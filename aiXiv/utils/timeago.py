from datetime import datetime, timezone


def timeago(dt: datetime | None) -> str:
    """Human-readable relative time, e.g. '3 h ago'. Treats naive datetimes as UTC
    (SQLite drops tz info, but we always store UTC)."""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = max((datetime.now(timezone.utc) - dt).total_seconds(), 0)

    if secs < 60:
        return "just now"
    mins = secs / 60
    if mins < 60:
        return f"{int(mins)} min ago"
    hours = mins / 60
    if hours < 24:
        return f"{int(hours)} h ago"
    days = hours / 24
    if days < 7:
        return f"{int(days)} d ago"
    if days < 30:
        return f"{int(days / 7)} wk ago"
    if days < 365:
        return f"{int(days / 30)} mo ago"
    return f"{int(days / 365)} yr ago"
