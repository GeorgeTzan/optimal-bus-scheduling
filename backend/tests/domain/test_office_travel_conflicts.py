"""Travel that falls inside an absence is a conflict, exactly as the verifier counts it."""
from app.domain.optimization.availability import transfer_conflicts
from app.domain.optimization.contracts import ResourceSnapshot, TripSnapshot

STATIONS, MATRIX = ('S1', 'S2'), ((0, 60), (60, 0))


def trip(trip_id, start, end, a, b):
    return TripSnapshot(trip_id, a, b, start, end, end - start)


def crew(windows):
    return ResourceSnapshot('R', '1', '1', '', available_windows=windows)


def test_travel_inside_an_absence_flags_both_trips_and_travel_in_usable_time_does_not():
    first, second = trip('A', 540, 600, 'S1', 'S1'), trip('B', 720, 800, 'S2', 'S2')  # A ends 10:00 at S1, B starts 12:00 at S2, travel 60
    assert transfer_conflicts(crew(((0, 600), (690, 1440))), [first, second], STATIONS, MATRIX) == {'A', 'B'}  # absence 10:00-11:30
    assert transfer_conflicts(crew(((0, 1440),)), [first, second], STATIONS, MATRIX) == set()
    assert transfer_conflicts(crew(None), [first, second], STATIONS, MATRIX) == set()
