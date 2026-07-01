import re
import json
import asyncio
import logging
import tempfile
from pathlib import Path

from aiXiv.settings import Defaults
from aiXiv.llm.base import LLMClient

logger = logging.getLogger("aiXiv.llm")


def _split_messages(messages: list[dict]) -> tuple[str, str]:
    """Collapse a chat message list into (system_text, user_text)."""
    system = "\n\n".join(
        m["content"] for m in messages if m.get("role") == "system" and m.get("content")
    )
    user = "\n\n".join(
        m["content"] for m in messages if m.get("role") != "system" and m.get("content")
    )
    return system, user


def _schema_instruction(schema: dict) -> str:
    return (
        "Respond with ONLY a single JSON object conforming to this JSON Schema. "
        "No prose, no explanation, no markdown code fences.\n"
        f"JSON Schema:\n{json.dumps(schema)}"
    )


def _extract_json(text: str) -> str:
    """Pull the JSON object out of a model reply (tolerates prose / ``` fences)."""
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text.strip()


def _strict_schema(node):
    """Return a copy with additionalProperties:false on every object (OpenAI strict mode)."""
    if isinstance(node, dict):
        out = {k: _strict_schema(v) for k, v in node.items()}
        if out.get("type") == "object":
            out.setdefault("additionalProperties", False)
        return out
    if isinstance(node, list):
        return [_strict_schema(x) for x in node]
    return node


async def _run(args: list[str], *, cwd: str, timeout: float = 180.0) -> tuple[str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"{args[0]} timed out after {timeout:.0f}s")
    if proc.returncode != 0:
        raise RuntimeError(
            f"{args[0]} failed (exit {proc.returncode}): "
            f"{err.decode(errors='replace').strip()[:800]}"
        )
    return out.decode(errors="replace"), err.decode(errors="replace")


class ClaudeCLIClient(LLMClient):
    """Routes generation through the local `claude` CLI (Claude Code) in print mode."""

    def __init__(self, model: str = ""):
        self.model = model

    async def generate(
        self,
        messages: list[dict],
        *,
        schema: dict | None = None,
        temperature: float = Defaults.LLM_TEMPERATURE,
    ) -> str:
        system, user = _split_messages(messages)
        if schema:
            system = f"{system}\n\n{_schema_instruction(schema)}".strip()

        # replace (not append to) Claude Code's agent system prompt and disable its
        # tools — otherwise the model may act on its coding-agent/memory instructions
        # instead of answering
        args = ["claude", "-p", user, "--output-format", "json", "--tools", ""]
        if self.model:
            args += ["--model", self.model]
        if system:
            args += ["--system-prompt", system]

        logger.info("claude-cli ▶ requesting model=%s", self.model or "(CLI default)")
        with tempfile.TemporaryDirectory() as cwd:
            raw, _ = await _run(args, cwd=cwd)

        envelope = json.loads(raw)
        if envelope.get("is_error"):
            raise RuntimeError(f"claude returned an error: {envelope.get('result')}")
        actual = ", ".join(envelope.get("modelUsage", {})) or "unknown"
        logger.info("claude-cli ◀ answered by model=%s", actual)
        text = envelope.get("result", "")
        return _extract_json(text) if schema else text

    async def list_models(self) -> list[str]:
        return ["sonnet", "haiku", "opus"]


class CodexCLIClient(LLMClient):
    """Routes generation through the local `codex exec` CLI (OpenAI Codex)."""

    def __init__(self, model: str = ""):
        self.model = model

    async def generate(
        self,
        messages: list[dict],
        *,
        schema: dict | None = None,
        temperature: float = Defaults.LLM_TEMPERATURE,
    ) -> str:
        system, user = _split_messages(messages)
        prompt = "\n\n".join(p for p in (system, user) if p)

        with tempfile.TemporaryDirectory() as cwd:
            out_file = Path(cwd) / "last.txt"
            args = [
                "codex",
                "exec",
                prompt,
                "-s",
                "read-only",
                "--skip-git-repo-check",
                "--color",
                "never",
                "-o",
                str(out_file),
            ]
            if self.model:
                args += ["-m", self.model]
            if schema:
                schema_file = Path(cwd) / "schema.json"
                schema_file.write_text(json.dumps(_strict_schema(schema)))
                args += ["--output-schema", str(schema_file)]

            logger.info(
                "codex-cli ▶ requesting model=%s", self.model or "(CLI default)"
            )
            out, err = await _run(args, cwd=cwd)
            banner = re.search(r"^model:\s*(.+)$", out + "\n" + err, re.MULTILINE)
            logger.info(
                "codex-cli ◀ answered by model=%s",
                banner.group(1).strip() if banner else "unknown",
            )
            text = out_file.read_text() if out_file.exists() else ""

        return _extract_json(text) if schema else text.strip()

    async def list_models(self) -> list[str]:
        """Read the model list codex itself caches from the OpenAI backend.

        Undocumented internal (refreshed by the CLI on use), hence the fallback.
        """
        cache = Path.home() / ".codex" / "models_cache.json"
        try:
            models = json.loads(cache.read_text())["models"]
            return [m["slug"] for m in models if "auto-review" not in m["slug"]]
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            return []
