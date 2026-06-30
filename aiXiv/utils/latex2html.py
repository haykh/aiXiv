import html
import re
from markupsafe import Markup

_LATEX_TEXT = [
    (re.compile(r"\\textit\{([^{}]*)\}"), r"<em>\1</em>"),
    (re.compile(r"\\emph\{([^{}]*)\}"), r"<em>\1</em>"),
    (re.compile(r"\\textbf\{([^{}]*)\}"), r"<strong>\1</strong>"),
    (re.compile(r"\\texttt\{([^{}]*)\}"), r"<code>\1</code>"),
    (re.compile(r"\{\\it\s+([^{}]*)\}"), r"<em>\1</em>"),
    (re.compile(r"\{\\bf\s+([^{}]*)\}"), r"<strong>\1</strong>"),
    (re.compile(r"\{\\tt\s+([^{}]*)\}"), r"<code>\1</code>"),
]


def _is_escaped(text: str, pos: int) -> bool:
    backslashes = 0
    cursor = pos - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1

    return backslashes % 2 == 1


def _find_unescaped_dollar(text: str, start: int) -> int:
    while True:
        pos = text.find("$", start)
        if pos == -1:
            return -1

        if not _is_escaped(text, pos):
            return pos

        start = pos + 1


def _find_unescaped_delimiter(text: str, delimiter: str, start: int) -> int:
    while True:
        pos = text.find(delimiter, start)
        if pos == -1:
            return -1

        if _is_escaped(text, pos):
            start = pos + len(delimiter)
            continue

        if delimiter == "$" and text.startswith("$$", pos):
            start = pos + 2
            continue

        return pos


def _replace_latex_text(text: str) -> str:
    for pat, repl in _LATEX_TEXT:
        text = pat.sub(repl, text)
    return text


def _replace_latex_text_outside_math(text: str) -> str:
    chunks = []
    pos = 0

    while pos < len(text):
        math_start = _find_unescaped_dollar(text, pos)
        if math_start == -1:
            chunks.append(_replace_latex_text(text[pos:]))
            break

        delimiter = "$$" if text.startswith("$$", math_start) else "$"
        math_end = _find_unescaped_delimiter(
            text, delimiter, math_start + len(delimiter)
        )
        if math_end == -1:
            chunks.append(_replace_latex_text(text[pos:]))
            break

        chunks.append(_replace_latex_text(text[pos:math_start]))
        pos = math_end + len(delimiter)
        chunks.append(text[math_start:pos])

    return "".join(chunks)


def latex_to_html(text: str) -> Markup:
    text = html.escape(text)
    text = _replace_latex_text_outside_math(text)
    return Markup(text)
