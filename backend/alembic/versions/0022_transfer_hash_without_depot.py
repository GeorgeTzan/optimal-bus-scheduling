"""Travel time confirmations no longer depend on a station's depot flag."""
import hashlib
import itertools
import json

from alembic import op

revision = '0022_transfer_hash_without_depot'
down_revision = '0021_management_reports'
branch_labels = None
depends_on = None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def transfer_facts(station_id, is_active, latitude, longitude):
    return {'id': station_id, 'is_active': is_active, 'latitude': latitude, 'longitude': longitude}


def legacy_facts(station_id, is_active, is_depot, latitude, longitude):
    return {'id': station_id, 'is_active': is_active, 'is_depot': is_depot, 'latitude': latitude, 'longitude': longitude}


def rewritten_hash(stored_hash, origin, destination):
    for origin_depot, destination_depot in itertools.product((True, False, None), repeat=2):
        legacy = fingerprint([legacy_facts(origin[0], origin[1], origin_depot, origin[3], origin[4]),
                              legacy_facts(destination[0], destination[1], destination_depot, destination[3], destination[4])])
        if stored_hash == legacy:
            return fingerprint([transfer_facts(origin[0], origin[1], origin[3], origin[4]),
                                transfer_facts(destination[0], destination[1], destination[3], destination[4])])
    return None


def upgrade():
    connection = op.get_bind()
    stations = {(row.tenant_id, row.id): (row.id, row.is_active, row.is_depot, row.latitude, row.longitude)
                for row in connection.exec_driver_sql('SELECT tenant_id,id,is_active,is_depot,latitude,longitude FROM domain_stations')}
    transfers = connection.exec_driver_sql(
        'SELECT id,tenant_id,origin_station_id,destination_station_id,confirmed_source_hash FROM domain_station_transfers WHERE confirmed_source_hash IS NOT NULL').all()
    for transfer_id, tenant_id, origin_id, destination_id, stored_hash in transfers:
        origin = stations.get((tenant_id, origin_id))
        destination = stations.get((tenant_id, destination_id))
        if origin is None or destination is None:
            continue
        replacement = rewritten_hash(stored_hash, origin, destination)
        if replacement is not None and replacement != stored_hash:
            connection.exec_driver_sql('UPDATE domain_station_transfers SET confirmed_source_hash=%s WHERE id=%s', (replacement, transfer_id))


def downgrade():
    pass
