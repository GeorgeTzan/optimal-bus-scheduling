"""Pure geometry for frozen usable windows (minutes from the frozen service-day origin). Used by the search and by the verifier."""


def _inside(windows, start: int, end: int) -> bool:
    return any(window_start <= start and end <= window_end for window_start, window_end in windows)


def availability_allows_trip(resource, trip) -> bool:
    """None means a legacy snapshot with no availability facts; callers decide whether that is acceptable."""
    windows = resource.available_windows
    return windows is None or _inside(windows, trip.start_minutes, trip.end_minutes)


def availability_allows_transition(resource, previous_trip, next_trip, transfer_minutes: int) -> bool:
    """Required travel must fit inside one usable window, anywhere between the previous trip's end and the next trip's start. An absence is never travel time."""
    windows = resource.available_windows
    if windows is None or transfer_minutes <= 0:
        return True
    return any(max(start, previous_trip.end_minutes) + transfer_minutes <= min(end, next_trip.start_minutes) for start, end in windows)


def transfer_conflicts(resource, trips, stations, matrix) -> set[str]:
    """Ids of consecutive trips of one crew whose required travel does not fit inside a usable window. Mirrors the verifier's transition rule."""
    found: set[str] = set()
    ordered = sorted(trips, key=lambda t: (t.start_minutes, t.end_minutes))
    for previous, following in zip(ordered, ordered[1:]):
        if previous.end_station == following.start_station:
            continue
        try:
            needed = matrix[stations.index(previous.end_station)][stations.index(following.start_station)]
        except (ValueError, IndexError, TypeError):
            continue
        if type(needed) is int and not availability_allows_transition(resource, previous, following, needed):
            found.update((previous.id, following.id))
    return found
