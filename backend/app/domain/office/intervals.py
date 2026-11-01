"""Half-open UTC intervals [start, end): adjacent endpoints never overlap."""
from datetime import datetime
from zoneinfo import ZoneInfo
from app.domain.timetables.time_service import LocalTimeResolutionError, _resolve_wall_clock

Interval = tuple[datetime, datetime]


def overlaps(first: Interval, second: Interval) -> bool:
    return first[0] < second[1] and second[0] < first[1]


def merge(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract(base: list[Interval], blockers: list[Interval]) -> list[Interval]:
    blocks, result = merge(blockers), []
    for start, end in merge(base):
        cursor = start
        for block_start, block_end in blocks:
            if block_end <= cursor:
                continue
            if block_start >= end:
                break
            if block_start > cursor:
                result.append((cursor, block_start))
            cursor = max(cursor, block_end)
        if cursor < end:
            result.append((cursor, end))
    return result


def normalize_office_interval(start_local: datetime, end_local: datetime | None, zone: str,
                              fold_start: int | None, fold_end: int | None) -> tuple[datetime, datetime | None]:
    """Resolve organization-local wall clocks to UTC. A DST gap or fold raises until staff choose explicitly."""
    tz = ZoneInfo(zone)

    def resolve(value, fold, field):
        try:
            return _resolve_wall_clock(value, tz, fold, field)
        except LocalTimeResolutionError as error:
            for issue in error.issues:
                issue['field'] = field
            raise

    start = resolve(start_local, fold_start, 'start_local')
    end = None if end_local is None else resolve(end_local, fold_end, 'end_local')
    if end is not None and end <= start:
        raise ValueError('The end must be after the start.')
    return start, end
