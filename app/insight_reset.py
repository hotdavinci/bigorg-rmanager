"""Filter remote history after an explicitly requested local Insights reset."""
from datetime import datetime, timezone


def include_after_reset(published_at: str | None, reset_at: str | None) -> bool:
    if not reset_at:
        return True
    if not published_at:
        return False
    try:
        def parse(value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        return parse(published_at) >= parse(reset_at)
    except (ValueError, TypeError):
        return False
