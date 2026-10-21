"""Daily quantities encoded alongside legacy interval rules; no data migration."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import random

WINDOWED_RULE = "windows:12-18"
RECURRING_WINDOWED_RULE = "recurring:windows:12-18"
POSTING_WINDOWS = ((8 * 60 + 30, 9 * 60 + 30),
                   (11 * 60 + 30, 12 * 60 + 30),
                   (17 * 60 + 30, 18 * 60 + 30))


def is_windowed(values: list[str]) -> bool:
    return values in ([WINDOWED_RULE], [RECURRING_WINDOWED_RULE])


def is_recurring(values: list[str]) -> bool:
    return values == [RECURRING_WINDOWED_RULE]


def windowed_ranges(current: date, now: datetime, not_before: datetime | None,
                    campaign_id: int, account_id: int,
                    horizon: datetime | None = None) -> list[tuple[int, int]]:
    """One stable 12–18 draw per window, prorated to available whole minutes."""
    day_start = datetime.combine(current, time())
    earliest = max(now + timedelta(minutes=5), not_before or day_start)
    first_minute = max(0, int(-(-(earliest - day_start).total_seconds() // 60)))
    result = []
    for window_index, (start, end) in enumerate(POSTING_WINDOWS):
        draw = random.Random(f"window:{campaign_id}:{account_id}:{current}:{window_index}").randint(12, 18)
        for i in range(draw):
            low = start + i * 60 // draw
            high = start + (i + 1) * 60 // draw - 1
            if high >= first_minute and (horizon is None or day_start + timedelta(minutes=high) < horizon):
                result.append((max(low, first_minute), high))
    return result


def daily_quantity(values: list[str]) -> int | None:
    if len(values) == 1 and values[0].startswith("daily:"):
        count = int(values[0].split(":", 1)[1])
        if not 1 <= count <= 1440:
            raise ValueError("Informe entre 1 e 1440 Reels por dia")
        return count
    return None


def utc_deadline_local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)


def daily_ranges(count: int, current: date, now: datetime,
                 not_before: datetime | None = None) -> list[tuple[int, int]]:
    """Disjoint minute buckets across the available portion of a local day."""
    if not 1 <= count <= 1440:
        raise ValueError("Informe entre 1 e 1440 Reels por dia")
    start = datetime.combine(current, time())
    end = start + timedelta(days=1)
    earliest = max(start, now + timedelta(minutes=5), not_before or start)
    if earliest >= end:
        return []
    # Round up rather than scheduling before a deadline with nonzero seconds.
    low = int((earliest - start).total_seconds() // 60)
    if earliest.second or earliest.microsecond:
        low += 1
    available = 1440 - low
    if available < count:
        raise ValueError("Não há minutos suficientes no dia para essa quantidade. Reduza os Reels ou escolha uma data futura.")
    return [(low + i * available // count,
             low + (i + 1) * available // count - 1) for i in range(count)]
