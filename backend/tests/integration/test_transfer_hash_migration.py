from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

path = Path(__file__).resolve().parents[2] / 'alembic/versions/0022_transfer_hash_without_depot.py'
spec = spec_from_file_location('transfer_hash_migration', path)
migration = module_from_spec(spec)
spec.loader.exec_module(migration)

ORIGIN = (1, True, True, 38.1, 21.1)
DESTINATION = (2, True, False, 38.2, 21.2)
CURRENT = migration.fingerprint([migration.transfer_facts(1, True, 38.1, 21.1), migration.transfer_facts(2, True, 38.2, 21.2)])


def legacy(origin_depot, destination_depot):
    return migration.fingerprint([migration.legacy_facts(1, True, origin_depot, 38.1, 21.1), migration.legacy_facts(2, True, destination_depot, 38.2, 21.2)])


def test_legacy_hash_under_any_depot_combination_is_rewritten():
    for origin_depot in (True, False, None):
        for destination_depot in (True, False, None):
            assert migration.rewritten_hash(legacy(origin_depot, destination_depot), ORIGIN, DESTINATION) == CURRENT


def test_hash_invalidated_by_location_or_activity_is_left_alone():
    stale = migration.fingerprint([migration.legacy_facts(1, True, True, 10.0, 21.1), migration.legacy_facts(2, True, False, 38.2, 21.2)])
    assert migration.rewritten_hash(stale, ORIGIN, DESTINATION) is None
    assert migration.rewritten_hash(legacy(True, False), (1, False, True, 38.1, 21.1), DESTINATION) is None
