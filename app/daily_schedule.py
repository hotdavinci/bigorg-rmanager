"""Daily quantities encoded alongside legacy interval rules; no data migration."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import random
import re

WINDOWED_RULE = "windows:12-18"
RECURRING_WINDOWED_RULE = "recurring:windows:12-18"
POSTING_WINDOWS = ((8 * 60 + 30, 9 * 60 + 30),
                   (11 * 60 + 30, 12 * 60 + 30),
                   (17 * 60 + 30, 18 * 60 + 30))
CUSTOM_WINDOW_PREFIX = "recurring:window:"


def window_specs(values: list[str]) -> list[tuple[int, int, int, int]]:
    """Daily windows as start, exclusive end, minimum and maximum posts."""
    if values in ([WINDOWED_RULE], [RECURRING_WINDOWED_RULE]):
        return [(start, end, 12, 18) for start, end in POSTING_WINDOWS]
    if not values or not all(value.startswith(CUSTOM_WINDOW_PREFIX) for value in values):
        raise ValueError("Informe ao menos um intervalo de publicação")
    if len(values) > 24:
        raise ValueError("Use no máximo 24 intervalos")
    specs = []
    for value in values:
        match = re.fullmatch(r"recurring:window:(\d{2}):(\d{2})-(\d{2}):(\d{2}):(\d+)-(\d+)", value)
        if not match:
            raise ValueError("Intervalo inválido. Use HH:MM-HH:MM e uma quantidade mínima e máxima")
        start_hour, start_minute, end_hour, end_minute, minimum, maximum = map(int, match.groups())
        if max(start_hour, end_hour) > 23 or max(start_minute, end_minute) > 59:
            raise ValueError("Horário inválido no intervalo")
        start = start_hour * 60 + start_minute
        end = end_hour * 60 + end_minute
        if end <= start:
            raise ValueError("O fim do intervalo deve ser posterior ao início no mesmo dia")
        if not 1 <= minimum <= maximum <= end - start:
            raise ValueError("A quantidade deve caber nos minutos do intervalo")
        specs.append((start, end, minimum, maximum))
    specs.sort()
    if any(right[0] < left[1] for left, right in zip(specs, specs[1:])):
        raise ValueError("Os intervalos não podem se sobrepor")
    return specs


def is_windowed(values: list[str]) -> bool:
    return values in ([WINDOWED_RULE], [RECURRING_WINDOWED_RULE]) or bool(values) and all(value.startswith(CUSTOM_WINDOW_PREFIX) for value in values)


def is_recurring(values: list[str]) -> bool:
    return values == [RECURRING_WINDOWED_RULE] or bool(values) and all(value.startswith(CUSTOM_WINDOW_PREFIX) for value in values)


def windowed_ranges(current: date, now: datetime, not_before: datetime | None,
                    campaign_id: int, account_id: int,
                    horizon: datetime | None = None,
                    values: list[str] | None = None) -> list[tuple[int, int]]:
    """Stable draw per configured window, prorated to available whole minutes."""
    day_start = datetime.combine(current, time())
    earliest = max(now + timedelta(minutes=5), not_before or day_start)
    first_minute = max(0, int(-(-(earliest - day_start).total_seconds() // 60)))
    result = []
    for window_index, (start, end, minimum, maximum) in enumerate(window_specs(values or [RECURRING_WINDOWED_RULE])):
        draw = random.Random(f"window:{campaign_id}:{account_id}:{current}:{window_index}").randint(minimum, maximum)
        for i in range(draw):
            low = start + i * (end - start) // draw
            high = start + (i + 1) * (end - start) // draw - 1
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
