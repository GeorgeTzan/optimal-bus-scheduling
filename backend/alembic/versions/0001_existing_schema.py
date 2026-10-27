"""Frozen baseline for the pre-migration application schema. Never import runtime models here."""
from alembic import op

revision = '0001_existing_schema'
down_revision = None
branch_labels = None
depends_on = None

EXPECTED_COLUMNS = {'ktels': {'id': {'type': 'INTEGER', 'nullable': False},
           'name': {'type': 'VARCHAR', 'nullable': True},
           'region': {'type': 'VARCHAR', 'nullable': True},
           'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_drivers': {'id': {'type': 'INTEGER', 'nullable': False},
                    'tenant_id': {'type': 'INTEGER', 'nullable': False},
                    'code': {'type': 'VARCHAR', 'nullable': False},
                    'first_name': {'type': 'VARCHAR', 'nullable': False},
                    'last_name': {'type': 'VARCHAR', 'nullable': False},
                    'phone': {'type': 'VARCHAR', 'nullable': True},
                    'license_number': {'type': 'VARCHAR', 'nullable': True},
                    'home_station_id': {'type': 'INTEGER', 'nullable': True},
                    'max_daily_driving_minutes': {'type': 'INTEGER', 'nullable': True},
                    'max_continuous_driving_minutes': {'type': 'INTEGER', 'nullable': True},
                    'min_daily_rest_minutes': {'type': 'INTEGER', 'nullable': True},
                    'is_active': {'type': 'BOOLEAN', 'nullable': True},
                    'properties': {'type': 'JSON', 'nullable': True},
                    'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_incidents': {'id': {'type': 'INTEGER', 'nullable': False},
                      'tenant_id': {'type': 'INTEGER', 'nullable': False},
                      'incident_type': {'type': 'VARCHAR', 'nullable': False},
                      'resource_id': {'type': 'VARCHAR', 'nullable': True},
                      'trip_id': {'type': 'VARCHAR', 'nullable': True},
                      'description': {'type': 'VARCHAR', 'nullable': False},
                      'reported_by': {'type': 'VARCHAR', 'nullable': False},
                      'status': {'type': 'VARCHAR', 'nullable': False},
                      'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True},
                      'resolved_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_jobs': {'id': {'type': 'INTEGER', 'nullable': False},
                 'job_id': {'type': 'VARCHAR', 'nullable': False},
                 'tenant_id': {'type': 'INTEGER', 'nullable': False},
                 'snapshot_id': {'type': 'VARCHAR', 'nullable': False},
                 'solver_version': {'type': 'VARCHAR', 'nullable': False},
                 'config': {'type': 'JSON', 'nullable': True},
                 'idempotency_key': {'type': 'VARCHAR', 'nullable': True},
                 'status': {'type': 'VARCHAR', 'nullable': True},
                 'attempt_token': {'type': 'INTEGER', 'nullable': False},
                 'claimed_by': {'type': 'VARCHAR', 'nullable': True},
                 'claimed_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True},
                 'lease_expires_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True},
                 'heartbeat_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True},
                 'progress_pct': {'type': 'INTEGER', 'nullable': True},
                 'error_message': {'type': 'VARCHAR', 'nullable': True},
                 'result_data': {'type': 'JSON', 'nullable': True},
                 'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True},
                 'updated_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_outbox_events': {'id': {'type': 'INTEGER', 'nullable': False},
                          'tenant_id': {'type': 'INTEGER', 'nullable': False},
                          'event_type': {'type': 'VARCHAR', 'nullable': False},
                          'job_id': {'type': 'VARCHAR', 'nullable': False},
                          'payload': {'type': 'JSON', 'nullable': True},
                          'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_scheduling_audit_logs': {'id': {'type': 'INTEGER', 'nullable': False},
                                  'tenant_id': {'type': 'INTEGER', 'nullable': False},
                                  'revision_id': {'type': 'VARCHAR', 'nullable': False},
                                  'action': {'type': 'VARCHAR', 'nullable': False},
                                  'actor': {'type': 'VARCHAR', 'nullable': False},
                                  'details': {'type': 'JSON', 'nullable': True},
                                  'timestamp': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_scheduling_periods': {'id': {'type': 'INTEGER', 'nullable': False},
                               'tenant_id': {'type': 'INTEGER', 'nullable': False},
                               'name': {'type': 'VARCHAR', 'nullable': False},
                               'start_date': {'type': 'DATE', 'nullable': False},
                               'end_date': {'type': 'DATE', 'nullable': False},
                               'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_stations': {'id': {'type': 'INTEGER', 'nullable': False},
                     'tenant_id': {'type': 'INTEGER', 'nullable': False},
                     'code': {'type': 'VARCHAR', 'nullable': False},
                     'name_el': {'type': 'VARCHAR', 'nullable': False},
                     'name_en': {'type': 'VARCHAR', 'nullable': False},
                     'is_depot': {'type': 'BOOLEAN', 'nullable': True},
                     'latitude': {'type': 'FLOAT', 'nullable': True},
                     'longitude': {'type': 'FLOAT', 'nullable': True}},
 'domain_vehicles': {'id': {'type': 'INTEGER', 'nullable': False},
                     'tenant_id': {'type': 'INTEGER', 'nullable': False},
                     'registration_plate': {'type': 'VARCHAR', 'nullable': False},
                     'bus_type': {'type': 'VARCHAR', 'nullable': False},
                     'capacity': {'type': 'INTEGER', 'nullable': True},
                     'home_station_id': {'type': 'INTEGER', 'nullable': True},
                     'is_active': {'type': 'BOOLEAN', 'nullable': True},
                     'properties': {'type': 'JSON', 'nullable': True},
                     'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'users': {'id': {'type': 'INTEGER', 'nullable': False},
           'email': {'type': 'VARCHAR', 'nullable': True},
           'hashed_password': {'type': 'VARCHAR', 'nullable': True},
           'full_name': {'type': 'VARCHAR', 'nullable': True},
           'is_active': {'type': 'BOOLEAN', 'nullable': True},
           'is_admin': {'type': 'BOOLEAN', 'nullable': True},
           'ktel_id': {'type': 'INTEGER', 'nullable': True},
           'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_driver_availabilities': {'id': {'type': 'INTEGER', 'nullable': False},
                                  'tenant_id': {'type': 'INTEGER', 'nullable': False},
                                  'driver_id': {'type': 'INTEGER', 'nullable': False},
                                  'service_date': {'type': 'DATE', 'nullable': False},
                                  'start_time_utc': {'type': 'TIMESTAMP WITHOUT TIME ZONE',
                                                     'nullable': False},
                                  'end_time_utc': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': False},
                                  'status': {'type': 'VARCHAR', 'nullable': True}},
 'domain_driver_qualifications': {'id': {'type': 'INTEGER', 'nullable': False},
                                  'tenant_id': {'type': 'INTEGER', 'nullable': False},
                                  'driver_id': {'type': 'INTEGER', 'nullable': False},
                                  'qualification_code': {'type': 'VARCHAR', 'nullable': False},
                                  'valid_until': {'type': 'DATE', 'nullable': True}},
 'domain_recovery_proposals': {'id': {'type': 'INTEGER', 'nullable': False},
                               'tenant_id': {'type': 'INTEGER', 'nullable': False},
                               'incident_id': {'type': 'INTEGER', 'nullable': False},
                               'as_of_minutes': {'type': 'INTEGER', 'nullable': False},
                               'reassignments': {'type': 'JSON', 'nullable': False},
                               'status': {'type': 'VARCHAR', 'nullable': False},
                               'approved_by': {'type': 'VARCHAR', 'nullable': True},
                               'approved_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True},
                               'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_routes': {'id': {'type': 'INTEGER', 'nullable': False},
                   'tenant_id': {'type': 'INTEGER', 'nullable': False},
                   'origin_station_id': {'type': 'INTEGER', 'nullable': False},
                   'destination_station_id': {'type': 'INTEGER', 'nullable': False},
                   'distance_km': {'type': 'FLOAT', 'nullable': True},
                   'typical_duration_minutes': {'type': 'INTEGER', 'nullable': True}},
 'domain_schedule_revisions': {'id': {'type': 'INTEGER', 'nullable': False},
                               'revision_id': {'type': 'VARCHAR', 'nullable': False},
                               'tenant_id': {'type': 'INTEGER', 'nullable': False},
                               'period_id': {'type': 'INTEGER', 'nullable': False},
                               'parent_revision_id': {'type': 'VARCHAR', 'nullable': True},
                               'version': {'type': 'INTEGER', 'nullable': False},
                               'status': {'type': 'VARCHAR', 'nullable': False},
                               'author': {'type': 'VARCHAR', 'nullable': False},
                               'comment': {'type': 'VARCHAR', 'nullable': True},
                               'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True},
                               'updated_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_vehicle_availabilities': {'id': {'type': 'INTEGER', 'nullable': False},
                                   'tenant_id': {'type': 'INTEGER', 'nullable': False},
                                   'vehicle_id': {'type': 'INTEGER', 'nullable': False},
                                   'service_date': {'type': 'DATE', 'nullable': False},
                                   'start_time_utc': {'type': 'TIMESTAMP WITHOUT TIME ZONE',
                                                      'nullable': False},
                                   'end_time_utc': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': False},
                                   'status': {'type': 'VARCHAR', 'nullable': True}},
 'schedules': {'id': {'type': 'INTEGER', 'nullable': False},
               'name': {'type': 'VARCHAR', 'nullable': True},
               'date': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True},
               'status': {'type': 'VARCHAR', 'nullable': True},
               'ktel_id': {'type': 'INTEGER', 'nullable': True},
               'created_by_id': {'type': 'INTEGER', 'nullable': True},
               'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_approval_requests': {'id': {'type': 'INTEGER', 'nullable': False},
                              'request_id': {'type': 'VARCHAR', 'nullable': False},
                              'tenant_id': {'type': 'INTEGER', 'nullable': False},
                              'revision_id': {'type': 'VARCHAR', 'nullable': False},
                              'requested_by': {'type': 'VARCHAR', 'nullable': False},
                              'status': {'type': 'VARCHAR', 'nullable': False},
                              'reviewer': {'type': 'VARCHAR', 'nullable': True},
                              'review_comment': {'type': 'VARCHAR', 'nullable': True},
                              'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True},
                              'reviewed_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_publications': {'id': {'type': 'INTEGER', 'nullable': False},
                         'publication_id': {'type': 'VARCHAR', 'nullable': False},
                         'tenant_id': {'type': 'INTEGER', 'nullable': False},
                         'revision_id': {'type': 'VARCHAR', 'nullable': False},
                         'published_by': {'type': 'VARCHAR', 'nullable': False},
                         'verification_report': {'type': 'JSON', 'nullable': False},
                         'published_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'domain_revision_assignments': {'id': {'type': 'INTEGER', 'nullable': False},
                                 'tenant_id': {'type': 'INTEGER', 'nullable': False},
                                 'revision_id': {'type': 'VARCHAR', 'nullable': False},
                                 'trip_id': {'type': 'VARCHAR', 'nullable': False},
                                 'resource_id': {'type': 'VARCHAR', 'nullable': False},
                                 'start_minutes': {'type': 'INTEGER', 'nullable': False},
                                 'end_minutes': {'type': 'INTEGER', 'nullable': False},
                                 'start_station': {'type': 'VARCHAR', 'nullable': False},
                                 'end_station': {'type': 'VARCHAR', 'nullable': False},
                                 'is_locked': {'type': 'BOOLEAN', 'nullable': False}},
 'domain_revision_snapshots': {'revision_id': {'type': 'VARCHAR', 'nullable': False},
                               'tenant_id': {'type': 'INTEGER', 'nullable': False},
                               'problem_data': {'type': 'JSON', 'nullable': False},
                               'source_data': {'type': 'JSON', 'nullable': False}},
 'domain_service_templates': {'id': {'type': 'INTEGER', 'nullable': False},
                              'tenant_id': {'type': 'INTEGER', 'nullable': False},
                              'route_id': {'type': 'INTEGER', 'nullable': False},
                              'trip_code': {'type': 'VARCHAR', 'nullable': False},
                              'departure_time': {'type': 'VARCHAR', 'nullable': False},
                              'arrival_time': {'type': 'VARCHAR', 'nullable': False},
                              'is_active': {'type': 'BOOLEAN', 'nullable': True}},
 'drivers': {'id': {'type': 'INTEGER', 'nullable': False},
             'ktel_id': {'type': 'INTEGER', 'nullable': True},
             'driver_code': {'type': 'VARCHAR', 'nullable': True},
             'bus_id': {'type': 'VARCHAR', 'nullable': True},
             'home_station': {'type': 'VARCHAR', 'nullable': True},
             'schedule_id': {'type': 'INTEGER', 'nullable': True},
             'properties': {'type': 'JSON', 'nullable': True}},
 'solutions': {'id': {'type': 'INTEGER', 'nullable': False},
               'ktel_id': {'type': 'INTEGER', 'nullable': True},
               'schedule_id': {'type': 'INTEGER', 'nullable': True},
               'assignments': {'type': 'JSON', 'nullable': True},
               'bus_states': {'type': 'JSON', 'nullable': True},
               'total_idle_time': {'type': 'INTEGER', 'nullable': True},
               'buses_used': {'type': 'INTEGER', 'nullable': True},
               'created_at': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': True}},
 'trips': {'id': {'type': 'INTEGER', 'nullable': False},
           'ktel_id': {'type': 'INTEGER', 'nullable': True},
           'trip_code': {'type': 'VARCHAR', 'nullable': True},
           'start_station': {'type': 'VARCHAR', 'nullable': True},
           'end_station': {'type': 'VARCHAR', 'nullable': True},
           'start_time': {'type': 'VARCHAR', 'nullable': True},
           'end_time': {'type': 'VARCHAR', 'nullable': True},
           'schedule_id': {'type': 'INTEGER', 'nullable': True},
           'properties': {'type': 'JSON', 'nullable': True}},
 'domain_trip_instances': {'id': {'type': 'INTEGER', 'nullable': False},
                           'tenant_id': {'type': 'INTEGER', 'nullable': False},
                           'trip_code': {'type': 'VARCHAR', 'nullable': False},
                           'service_date': {'type': 'DATE', 'nullable': False},
                           'origin_station_id': {'type': 'INTEGER', 'nullable': False},
                           'destination_station_id': {'type': 'INTEGER', 'nullable': False},
                           'start_utc': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': False},
                           'end_utc': {'type': 'TIMESTAMP WITHOUT TIME ZONE', 'nullable': False},
                           'template_id': {'type': 'INTEGER', 'nullable': True},
                           'properties': {'type': 'JSON', 'nullable': True}}}

EXPECTED_KEYS = {'ktels': {'primary_key': ['id'], 'foreign_keys': [], 'unique_indexes': [['name']]},
 'domain_drivers': {'primary_key': ['id'],
                    'foreign_keys': [{'columns': ['tenant_id'],
                                      'target_table': 'ktels',
                                      'target_columns': ['id']}],
                    'unique_indexes': []},
 'domain_incidents': {'primary_key': ['id'],
                      'foreign_keys': [{'columns': ['tenant_id'],
                                        'target_table': 'ktels',
                                        'target_columns': ['id']}],
                      'unique_indexes': []},
 'domain_jobs': {'primary_key': ['id'],
                 'foreign_keys': [{'columns': ['tenant_id'],
                                   'target_table': 'ktels',
                                   'target_columns': ['id']}],
                 'unique_indexes': [['job_id']]},
 'domain_outbox_events': {'primary_key': ['id'],
                          'foreign_keys': [{'columns': ['tenant_id'],
                                            'target_table': 'ktels',
                                            'target_columns': ['id']}],
                          'unique_indexes': []},
 'domain_scheduling_audit_logs': {'primary_key': ['id'],
                                  'foreign_keys': [{'columns': ['tenant_id'],
                                                    'target_table': 'ktels',
                                                    'target_columns': ['id']}],
                                  'unique_indexes': []},
 'domain_scheduling_periods': {'primary_key': ['id'],
                               'foreign_keys': [{'columns': ['tenant_id'],
                                                 'target_table': 'ktels',
                                                 'target_columns': ['id']}],
                               'unique_indexes': []},
 'domain_stations': {'primary_key': ['id'],
                     'foreign_keys': [{'columns': ['tenant_id'],
                                       'target_table': 'ktels',
                                       'target_columns': ['id']}],
                     'unique_indexes': []},
 'domain_vehicles': {'primary_key': ['id'],
                     'foreign_keys': [{'columns': ['tenant_id'],
                                       'target_table': 'ktels',
                                       'target_columns': ['id']}],
                     'unique_indexes': []},
 'users': {'primary_key': ['id'],
           'foreign_keys': [{'columns': ['ktel_id'], 'target_table': 'ktels', 'target_columns': ['id']}],
           'unique_indexes': [['email']]},
 'domain_driver_availabilities': {'primary_key': ['id'],
                                  'foreign_keys': [{'columns': ['tenant_id'],
                                                    'target_table': 'ktels',
                                                    'target_columns': ['id']},
                                                   {'columns': ['driver_id'],
                                                    'target_table': 'domain_drivers',
                                                    'target_columns': ['id']}],
                                  'unique_indexes': []},
 'domain_driver_qualifications': {'primary_key': ['id'],
                                  'foreign_keys': [{'columns': ['driver_id'],
                                                    'target_table': 'domain_drivers',
                                                    'target_columns': ['id']},
                                                   {'columns': ['tenant_id'],
                                                    'target_table': 'ktels',
                                                    'target_columns': ['id']}],
                                  'unique_indexes': []},
 'domain_recovery_proposals': {'primary_key': ['id'],
                               'foreign_keys': [{'columns': ['incident_id'],
                                                 'target_table': 'domain_incidents',
                                                 'target_columns': ['id']},
                                                {'columns': ['tenant_id'],
                                                 'target_table': 'ktels',
                                                 'target_columns': ['id']}],
                               'unique_indexes': []},
 'domain_routes': {'primary_key': ['id'],
                   'foreign_keys': [{'columns': ['destination_station_id'],
                                     'target_table': 'domain_stations',
                                     'target_columns': ['id']},
                                    {'columns': ['origin_station_id'],
                                     'target_table': 'domain_stations',
                                     'target_columns': ['id']},
                                    {'columns': ['tenant_id'],
                                     'target_table': 'ktels',
                                     'target_columns': ['id']}],
                   'unique_indexes': []},
 'domain_schedule_revisions': {'primary_key': ['id'],
                               'foreign_keys': [{'columns': ['tenant_id'],
                                                 'target_table': 'ktels',
                                                 'target_columns': ['id']},
                                                {'columns': ['period_id'],
                                                 'target_table': 'domain_scheduling_periods',
                                                 'target_columns': ['id']}],
                               'unique_indexes': [['revision_id']]},
 'domain_vehicle_availabilities': {'primary_key': ['id'],
                                   'foreign_keys': [{'columns': ['vehicle_id'],
                                                     'target_table': 'domain_vehicles',
                                                     'target_columns': ['id']},
                                                    {'columns': ['tenant_id'],
                                                     'target_table': 'ktels',
                                                     'target_columns': ['id']}],
                                   'unique_indexes': []},
 'schedules': {'primary_key': ['id'],
               'foreign_keys': [{'columns': ['ktel_id'],
                                 'target_table': 'ktels',
                                 'target_columns': ['id']},
                                {'columns': ['created_by_id'],
                                 'target_table': 'users',
                                 'target_columns': ['id']}],
               'unique_indexes': []},
 'domain_approval_requests': {'primary_key': ['id'],
                              'foreign_keys': [{'columns': ['revision_id'],
                                                'target_table': 'domain_schedule_revisions',
                                                'target_columns': ['revision_id']},
                                               {'columns': ['tenant_id'],
                                                'target_table': 'ktels',
                                                'target_columns': ['id']}],
                              'unique_indexes': [['request_id']]},
 'domain_publications': {'primary_key': ['id'],
                         'foreign_keys': [{'columns': ['revision_id'],
                                           'target_table': 'domain_schedule_revisions',
                                           'target_columns': ['revision_id']},
                                          {'columns': ['tenant_id'],
                                           'target_table': 'ktels',
                                           'target_columns': ['id']}],
                         'unique_indexes': [['publication_id']]},
 'domain_revision_assignments': {'primary_key': ['id'],
                                 'foreign_keys': [{'columns': ['revision_id'],
                                                   'target_table': 'domain_schedule_revisions',
                                                   'target_columns': ['revision_id']},
                                                  {'columns': ['tenant_id'],
                                                   'target_table': 'ktels',
                                                   'target_columns': ['id']}],
                                 'unique_indexes': []},
 'domain_revision_snapshots': {'primary_key': ['revision_id'],
                               'foreign_keys': [{'columns': ['revision_id'],
                                                 'target_table': 'domain_schedule_revisions',
                                                 'target_columns': ['revision_id']},
                                                {'columns': ['tenant_id'],
                                                 'target_table': 'ktels',
                                                 'target_columns': ['id']}],
                               'unique_indexes': []},
 'domain_service_templates': {'primary_key': ['id'],
                              'foreign_keys': [{'columns': ['route_id'],
                                                'target_table': 'domain_routes',
                                                'target_columns': ['id']},
                                               {'columns': ['tenant_id'],
                                                'target_table': 'ktels',
                                                'target_columns': ['id']}],
                              'unique_indexes': []},
 'drivers': {'primary_key': ['id'],
             'foreign_keys': [{'columns': ['schedule_id'],
                               'target_table': 'schedules',
                               'target_columns': ['id']},
                              {'columns': ['ktel_id'],
                               'target_table': 'ktels',
                               'target_columns': ['id']}],
             'unique_indexes': []},
 'solutions': {'primary_key': ['id'],
               'foreign_keys': [{'columns': ['ktel_id'],
                                 'target_table': 'ktels',
                                 'target_columns': ['id']},
                                {'columns': ['schedule_id'],
                                 'target_table': 'schedules',
                                 'target_columns': ['id']}],
               'unique_indexes': []},
 'trips': {'primary_key': ['id'],
           'foreign_keys': [{'columns': ['ktel_id'], 'target_table': 'ktels', 'target_columns': ['id']},
                            {'columns': ['schedule_id'],
                             'target_table': 'schedules',
                             'target_columns': ['id']}],
           'unique_indexes': []},
 'domain_trip_instances': {'primary_key': ['id'],
                           'foreign_keys': [{'columns': ['template_id'],
                                             'target_table': 'domain_service_templates',
                                             'target_columns': ['id']},
                                            {'columns': ['destination_station_id'],
                                             'target_table': 'domain_stations',
                                             'target_columns': ['id']},
                                            {'columns': ['origin_station_id'],
                                             'target_table': 'domain_stations',
                                             'target_columns': ['id']},
                                            {'columns': ['tenant_id'],
                                             'target_table': 'ktels',
                                             'target_columns': ['id']}],
                           'unique_indexes': []}}

DDL = ['\n'
 'CREATE TABLE ktels (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tname VARCHAR, \n'
 '\tregion VARCHAR, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_ktels_id ON ktels (id)',
 'CREATE UNIQUE INDEX ix_ktels_name ON ktels (name)',
 '\n'
 'CREATE TABLE domain_drivers (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tcode VARCHAR NOT NULL, \n'
 '\tfirst_name VARCHAR NOT NULL, \n'
 '\tlast_name VARCHAR NOT NULL, \n'
 '\tphone VARCHAR, \n'
 '\tlicense_number VARCHAR, \n'
 '\thome_station_id INTEGER, \n'
 '\tmax_daily_driving_minutes INTEGER, \n'
 '\tmax_continuous_driving_minutes INTEGER, \n'
 '\tmin_daily_rest_minutes INTEGER, \n'
 '\tis_active BOOLEAN, \n'
 '\tproperties JSON, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_drivers_code ON domain_drivers (code)',
 'CREATE INDEX ix_domain_drivers_id ON domain_drivers (id)',
 'CREATE INDEX ix_domain_drivers_tenant_id ON domain_drivers (tenant_id)',
 '\n'
 'CREATE TABLE domain_incidents (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tincident_type VARCHAR NOT NULL, \n'
 '\tresource_id VARCHAR, \n'
 '\ttrip_id VARCHAR, \n'
 '\tdescription VARCHAR NOT NULL, \n'
 '\treported_by VARCHAR NOT NULL, \n'
 '\tstatus VARCHAR NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tresolved_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_incidents_id ON domain_incidents (id)',
 'CREATE INDEX ix_domain_incidents_incident_type ON domain_incidents (incident_type)',
 'CREATE INDEX ix_domain_incidents_resource_id ON domain_incidents (resource_id)',
 'CREATE INDEX ix_domain_incidents_status ON domain_incidents (status)',
 'CREATE INDEX ix_domain_incidents_tenant_id ON domain_incidents (tenant_id)',
 'CREATE INDEX ix_domain_incidents_trip_id ON domain_incidents (trip_id)',
 '\n'
 'CREATE TABLE domain_jobs (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tjob_id VARCHAR NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tsnapshot_id VARCHAR NOT NULL, \n'
 '\tsolver_version VARCHAR NOT NULL, \n'
 '\tconfig JSON, \n'
 '\tidempotency_key VARCHAR, \n'
 '\tstatus VARCHAR, \n'
 '\tattempt_token INTEGER NOT NULL, \n'
 '\tclaimed_by VARCHAR, \n'
 '\tclaimed_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tlease_expires_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\theartbeat_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tprogress_pct INTEGER, \n'
 '\terror_message VARCHAR, \n'
 '\tresult_data JSON, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tupdated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_jobs_id ON domain_jobs (id)',
 'CREATE INDEX ix_domain_jobs_idempotency_key ON domain_jobs (idempotency_key)',
 'CREATE UNIQUE INDEX ix_domain_jobs_job_id ON domain_jobs (job_id)',
 'CREATE INDEX ix_domain_jobs_lease_expires_at ON domain_jobs (lease_expires_at)',
 'CREATE INDEX ix_domain_jobs_status ON domain_jobs (status)',
 'CREATE INDEX ix_domain_jobs_tenant_id ON domain_jobs (tenant_id)',
 '\n'
 'CREATE TABLE domain_outbox_events (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tevent_type VARCHAR NOT NULL, \n'
 '\tjob_id VARCHAR NOT NULL, \n'
 '\tpayload JSON, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_outbox_events_created_at ON domain_outbox_events (created_at)',
 'CREATE INDEX ix_domain_outbox_events_event_type ON domain_outbox_events (event_type)',
 'CREATE INDEX ix_domain_outbox_events_id ON domain_outbox_events (id)',
 'CREATE INDEX ix_domain_outbox_events_job_id ON domain_outbox_events (job_id)',
 'CREATE INDEX ix_domain_outbox_events_tenant_id ON domain_outbox_events (tenant_id)',
 '\n'
 'CREATE TABLE domain_scheduling_audit_logs (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\trevision_id VARCHAR NOT NULL, \n'
 '\taction VARCHAR NOT NULL, \n'
 '\tactor VARCHAR NOT NULL, \n'
 '\tdetails JSON, \n'
 '\ttimestamp TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_scheduling_audit_logs_action ON domain_scheduling_audit_logs (action)',
 'CREATE INDEX ix_domain_scheduling_audit_logs_id ON domain_scheduling_audit_logs (id)',
 'CREATE INDEX ix_domain_scheduling_audit_logs_revision_id ON domain_scheduling_audit_logs (revision_id)',
 'CREATE INDEX ix_domain_scheduling_audit_logs_tenant_id ON domain_scheduling_audit_logs (tenant_id)',
 '\n'
 'CREATE TABLE domain_scheduling_periods (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tname VARCHAR NOT NULL, \n'
 '\tstart_date DATE NOT NULL, \n'
 '\tend_date DATE NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_scheduling_periods_id ON domain_scheduling_periods (id)',
 'CREATE INDEX ix_domain_scheduling_periods_tenant_id ON domain_scheduling_periods (tenant_id)',
 '\n'
 'CREATE TABLE domain_stations (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tcode VARCHAR NOT NULL, \n'
 '\tname_el VARCHAR NOT NULL, \n'
 '\tname_en VARCHAR NOT NULL, \n'
 '\tis_depot BOOLEAN, \n'
 '\tlatitude FLOAT, \n'
 '\tlongitude FLOAT, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_stations_code ON domain_stations (code)',
 'CREATE INDEX ix_domain_stations_id ON domain_stations (id)',
 'CREATE INDEX ix_domain_stations_tenant_id ON domain_stations (tenant_id)',
 '\n'
 'CREATE TABLE domain_vehicles (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tregistration_plate VARCHAR NOT NULL, \n'
 '\tbus_type VARCHAR NOT NULL, \n'
 '\tcapacity INTEGER, \n'
 '\thome_station_id INTEGER, \n'
 '\tis_active BOOLEAN, \n'
 '\tproperties JSON, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_vehicles_id ON domain_vehicles (id)',
 'CREATE INDEX ix_domain_vehicles_registration_plate ON domain_vehicles (registration_plate)',
 'CREATE INDEX ix_domain_vehicles_tenant_id ON domain_vehicles (tenant_id)',
 '\n'
 'CREATE TABLE users (\n'
 '\tid SERIAL NOT NULL, \n'
 '\temail VARCHAR, \n'
 '\thashed_password VARCHAR, \n'
 '\tfull_name VARCHAR, \n'
 '\tis_active BOOLEAN, \n'
 '\tis_admin BOOLEAN, \n'
 '\tktel_id INTEGER, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(ktel_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE UNIQUE INDEX ix_users_email ON users (email)',
 'CREATE INDEX ix_users_id ON users (id)',
 '\n'
 'CREATE TABLE domain_driver_availabilities (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tdriver_id INTEGER NOT NULL, \n'
 '\tservice_date DATE NOT NULL, \n'
 '\tstart_time_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tend_time_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tstatus VARCHAR, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(driver_id) REFERENCES domain_drivers (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_driver_availabilities_driver_id ON domain_driver_availabilities (driver_id)',
 'CREATE INDEX ix_domain_driver_availabilities_id ON domain_driver_availabilities (id)',
 'CREATE INDEX ix_domain_driver_availabilities_service_date ON domain_driver_availabilities (service_date)',
 'CREATE INDEX ix_domain_driver_availabilities_tenant_id ON domain_driver_availabilities (tenant_id)',
 '\n'
 'CREATE TABLE domain_driver_qualifications (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tdriver_id INTEGER NOT NULL, \n'
 '\tqualification_code VARCHAR NOT NULL, \n'
 '\tvalid_until DATE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(driver_id) REFERENCES domain_drivers (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_driver_qualifications_driver_id ON domain_driver_qualifications (driver_id)',
 'CREATE INDEX ix_domain_driver_qualifications_id ON domain_driver_qualifications (id)',
 'CREATE INDEX ix_domain_driver_qualifications_tenant_id ON domain_driver_qualifications (tenant_id)',
 '\n'
 'CREATE TABLE domain_recovery_proposals (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tincident_id INTEGER NOT NULL, \n'
 '\tas_of_minutes INTEGER NOT NULL, \n'
 '\treassignments JSON NOT NULL, \n'
 '\tstatus VARCHAR NOT NULL, \n'
 '\tapproved_by VARCHAR, \n'
 '\tapproved_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(incident_id) REFERENCES domain_incidents (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_recovery_proposals_id ON domain_recovery_proposals (id)',
 'CREATE INDEX ix_domain_recovery_proposals_incident_id ON domain_recovery_proposals (incident_id)',
 'CREATE INDEX ix_domain_recovery_proposals_status ON domain_recovery_proposals (status)',
 'CREATE INDEX ix_domain_recovery_proposals_tenant_id ON domain_recovery_proposals (tenant_id)',
 '\n'
 'CREATE TABLE domain_routes (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\torigin_station_id INTEGER NOT NULL, \n'
 '\tdestination_station_id INTEGER NOT NULL, \n'
 '\tdistance_km FLOAT, \n'
 '\ttypical_duration_minutes INTEGER, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(origin_station_id) REFERENCES domain_stations (id), \n'
 '\tFOREIGN KEY(destination_station_id) REFERENCES domain_stations (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_routes_id ON domain_routes (id)',
 'CREATE INDEX ix_domain_routes_tenant_id ON domain_routes (tenant_id)',
 '\n'
 'CREATE TABLE domain_schedule_revisions (\n'
 '\tid SERIAL NOT NULL, \n'
 '\trevision_id VARCHAR NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tperiod_id INTEGER NOT NULL, \n'
 '\tparent_revision_id VARCHAR, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tstatus VARCHAR NOT NULL, \n'
 '\tauthor VARCHAR NOT NULL, \n'
 '\tcomment VARCHAR, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tupdated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(period_id) REFERENCES domain_scheduling_periods (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_schedule_revisions_id ON domain_schedule_revisions (id)',
 'CREATE INDEX ix_domain_schedule_revisions_parent_revision_id ON domain_schedule_revisions '
 '(parent_revision_id)',
 'CREATE INDEX ix_domain_schedule_revisions_period_id ON domain_schedule_revisions (period_id)',
 'CREATE UNIQUE INDEX ix_domain_schedule_revisions_revision_id ON domain_schedule_revisions (revision_id)',
 'CREATE INDEX ix_domain_schedule_revisions_status ON domain_schedule_revisions (status)',
 'CREATE INDEX ix_domain_schedule_revisions_tenant_id ON domain_schedule_revisions (tenant_id)',
 '\n'
 'CREATE TABLE domain_vehicle_availabilities (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tservice_date DATE NOT NULL, \n'
 '\tstart_time_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tend_time_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tstatus VARCHAR, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES domain_vehicles (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_vehicle_availabilities_id ON domain_vehicle_availabilities (id)',
 'CREATE INDEX ix_domain_vehicle_availabilities_service_date ON domain_vehicle_availabilities (service_date)',
 'CREATE INDEX ix_domain_vehicle_availabilities_tenant_id ON domain_vehicle_availabilities (tenant_id)',
 'CREATE INDEX ix_domain_vehicle_availabilities_vehicle_id ON domain_vehicle_availabilities (vehicle_id)',
 '\n'
 'CREATE TABLE schedules (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tname VARCHAR, \n'
 '\tdate TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tstatus VARCHAR, \n'
 '\tktel_id INTEGER, \n'
 '\tcreated_by_id INTEGER, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(ktel_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(created_by_id) REFERENCES users (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_schedules_id ON schedules (id)',
 '\n'
 'CREATE TABLE domain_approval_requests (\n'
 '\tid SERIAL NOT NULL, \n'
 '\trequest_id VARCHAR NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\trevision_id VARCHAR NOT NULL, \n'
 '\trequested_by VARCHAR NOT NULL, \n'
 '\tstatus VARCHAR NOT NULL, \n'
 '\treviewer VARCHAR, \n'
 '\treview_comment VARCHAR, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\treviewed_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(revision_id) REFERENCES domain_schedule_revisions (revision_id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_approval_requests_id ON domain_approval_requests (id)',
 'CREATE UNIQUE INDEX ix_domain_approval_requests_request_id ON domain_approval_requests (request_id)',
 'CREATE INDEX ix_domain_approval_requests_revision_id ON domain_approval_requests (revision_id)',
 'CREATE INDEX ix_domain_approval_requests_status ON domain_approval_requests (status)',
 'CREATE INDEX ix_domain_approval_requests_tenant_id ON domain_approval_requests (tenant_id)',
 '\n'
 'CREATE TABLE domain_publications (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tpublication_id VARCHAR NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\trevision_id VARCHAR NOT NULL, \n'
 '\tpublished_by VARCHAR NOT NULL, \n'
 '\tverification_report JSON NOT NULL, \n'
 '\tpublished_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(revision_id) REFERENCES domain_schedule_revisions (revision_id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_publications_id ON domain_publications (id)',
 'CREATE UNIQUE INDEX ix_domain_publications_publication_id ON domain_publications (publication_id)',
 'CREATE INDEX ix_domain_publications_revision_id ON domain_publications (revision_id)',
 'CREATE INDEX ix_domain_publications_tenant_id ON domain_publications (tenant_id)',
 '\n'
 'CREATE TABLE domain_revision_assignments (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\trevision_id VARCHAR NOT NULL, \n'
 '\ttrip_id VARCHAR NOT NULL, \n'
 '\tresource_id VARCHAR NOT NULL, \n'
 '\tstart_minutes INTEGER NOT NULL, \n'
 '\tend_minutes INTEGER NOT NULL, \n'
 '\tstart_station VARCHAR NOT NULL, \n'
 '\tend_station VARCHAR NOT NULL, \n'
 '\tis_locked BOOLEAN NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(revision_id) REFERENCES domain_schedule_revisions (revision_id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_revision_assignments_id ON domain_revision_assignments (id)',
 'CREATE INDEX ix_domain_revision_assignments_resource_id ON domain_revision_assignments (resource_id)',
 'CREATE INDEX ix_domain_revision_assignments_revision_id ON domain_revision_assignments (revision_id)',
 'CREATE INDEX ix_domain_revision_assignments_tenant_id ON domain_revision_assignments (tenant_id)',
 'CREATE INDEX ix_domain_revision_assignments_trip_id ON domain_revision_assignments (trip_id)',
 '\n'
 'CREATE TABLE domain_revision_snapshots (\n'
 '\trevision_id VARCHAR NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\tproblem_data JSON NOT NULL, \n'
 '\tsource_data JSON NOT NULL, \n'
 '\tPRIMARY KEY (revision_id), \n'
 '\tFOREIGN KEY(revision_id) REFERENCES domain_schedule_revisions (revision_id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_revision_snapshots_tenant_id ON domain_revision_snapshots (tenant_id)',
 '\n'
 'CREATE TABLE domain_service_templates (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\troute_id INTEGER NOT NULL, \n'
 '\ttrip_code VARCHAR NOT NULL, \n'
 '\tdeparture_time VARCHAR NOT NULL, \n'
 '\tarrival_time VARCHAR NOT NULL, \n'
 '\tis_active BOOLEAN, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(route_id) REFERENCES domain_routes (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_service_templates_id ON domain_service_templates (id)',
 'CREATE INDEX ix_domain_service_templates_tenant_id ON domain_service_templates (tenant_id)',
 'CREATE INDEX ix_domain_service_templates_trip_code ON domain_service_templates (trip_code)',
 '\n'
 'CREATE TABLE drivers (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tktel_id INTEGER, \n'
 '\tdriver_code VARCHAR, \n'
 '\tbus_id VARCHAR, \n'
 '\thome_station VARCHAR, \n'
 '\tschedule_id INTEGER, \n'
 '\tproperties JSON, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(ktel_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(schedule_id) REFERENCES schedules (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_drivers_driver_code ON drivers (driver_code)',
 'CREATE INDEX ix_drivers_id ON drivers (id)',
 'CREATE INDEX ix_drivers_ktel_id ON drivers (ktel_id)',
 '\n'
 'CREATE TABLE solutions (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tktel_id INTEGER, \n'
 '\tschedule_id INTEGER, \n'
 '\tassignments JSON, \n'
 '\tbus_states JSON, \n'
 '\ttotal_idle_time INTEGER, \n'
 '\tbuses_used INTEGER, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(ktel_id) REFERENCES ktels (id), \n'
 '\tUNIQUE (schedule_id), \n'
 '\tFOREIGN KEY(schedule_id) REFERENCES schedules (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_solutions_id ON solutions (id)',
 'CREATE INDEX ix_solutions_ktel_id ON solutions (ktel_id)',
 '\n'
 'CREATE TABLE trips (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tktel_id INTEGER, \n'
 '\ttrip_code VARCHAR, \n'
 '\tstart_station VARCHAR, \n'
 '\tend_station VARCHAR, \n'
 '\tstart_time VARCHAR, \n'
 '\tend_time VARCHAR, \n'
 '\tschedule_id INTEGER, \n'
 '\tproperties JSON, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(ktel_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(schedule_id) REFERENCES schedules (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_trips_id ON trips (id)',
 'CREATE INDEX ix_trips_ktel_id ON trips (ktel_id)',
 'CREATE INDEX ix_trips_trip_code ON trips (trip_code)',
 '\n'
 'CREATE TABLE domain_trip_instances (\n'
 '\tid SERIAL NOT NULL, \n'
 '\ttenant_id INTEGER NOT NULL, \n'
 '\ttrip_code VARCHAR NOT NULL, \n'
 '\tservice_date DATE NOT NULL, \n'
 '\torigin_station_id INTEGER NOT NULL, \n'
 '\tdestination_station_id INTEGER NOT NULL, \n'
 '\tstart_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tend_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\ttemplate_id INTEGER, \n'
 '\tproperties JSON, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(tenant_id) REFERENCES ktels (id), \n'
 '\tFOREIGN KEY(origin_station_id) REFERENCES domain_stations (id), \n'
 '\tFOREIGN KEY(destination_station_id) REFERENCES domain_stations (id), \n'
 '\tFOREIGN KEY(template_id) REFERENCES domain_service_templates (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_domain_trip_instances_id ON domain_trip_instances (id)',
 'CREATE INDEX ix_domain_trip_instances_service_date ON domain_trip_instances (service_date)',
 'CREATE INDEX ix_domain_trip_instances_tenant_id ON domain_trip_instances (tenant_id)',
 'CREATE INDEX ix_domain_trip_instances_trip_code ON domain_trip_instances (trip_code)']

TABLES = ['ktels', 'domain_drivers', 'domain_incidents', 'domain_jobs', 'domain_outbox_events', 'domain_scheduling_audit_logs', 'domain_scheduling_periods', 'domain_stations', 'domain_vehicles', 'users', 'domain_driver_availabilities', 'domain_driver_qualifications', 'domain_recovery_proposals', 'domain_routes', 'domain_schedule_revisions', 'domain_vehicle_availabilities', 'schedules', 'domain_approval_requests', 'domain_publications', 'domain_revision_assignments', 'domain_revision_snapshots', 'domain_service_templates', 'drivers', 'solutions', 'trips', 'domain_trip_instances']

def upgrade():
    for statement in DDL:
        op.execute(statement)


def downgrade():
    for table in reversed(TABLES):
        op.drop_table(table)
