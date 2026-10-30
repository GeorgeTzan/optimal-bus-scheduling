from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.database import Base, get_db
from db.models import KTEL, User
from tests.support import create_test_access_token
from main import app


@pytest.fixture
def setup(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "REFERENCE_TOOLS_ENABLED", True)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([KTEL(id=1, name='One'), KTEL(id=2, name='Two'),
                    User(id=1, email='admin@one.gr', ktel_id=1, is_admin=True),
                    User(id=2, email='admin@two.gr', ktel_id=2, is_admin=True),
                    User(id=3, email='reader@one.gr', ktel_id=1, is_admin=False)])
        db.commit()
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    def headers(uid):
        with factory() as db:
            return {'Authorization':'Bearer '+create_test_access_token(db,uid)}
    yield TestClient(app), headers
    app.dependency_overrides.clear()
    engine.dispose()


def initialize(client, headers):
    response = client.post('/api/v1/scheduling/revisions/import-reference', headers=headers,
                           json={'service_date': '2026-10-30'})
    assert response.status_code == 201, response.text
    return response.json()


def test_reload_patch_conflict_and_tenant_hiding(setup):
    client, auth = setup
    revision = initialize(client, auth(1))
    rid = revision['revision_id']
    assignment = revision['assignments'][0]
    payload = {'version': revision['version'], 'patches': [
        {'trip_id': assignment['trip_id'], 'new_resource_id': assignment['resource_id'], 'is_locked': True}]}
    url = f'/api/v1/scheduling/revisions/{rid}/patches'
    response = client.post(url, headers=auth(1), json=payload)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated['version'] == revision['version'] + 1
    loaded = client.get('/api/v1/scheduling/revisions/active?source_kind=reference_archive', headers=auth(1)).json()
    assert loaded == updated
    assert next(a for a in loaded['assignments'] if a['trip_id'] == assignment['trip_id'])['is_locked']
    assert client.post(url, headers=auth(1), json=payload).status_code == 409
    assert client.post(url, headers=auth(2), json=payload).status_code == 404
    assert client.get('/api/v1/scheduling/revisions/active?source_kind=reference_archive', headers=auth(2)).status_code == 404
    assert client.post(url, headers=auth(3), json=payload).status_code == 403
    assert client.get('/api/v1/scheduling/revisions/active?source_kind=reference_archive').status_code in (401, 403)


def test_invalid_edit_persists_verified_draft_and_blocks_publication(setup):
    client, auth = setup
    revision = initialize(client, auth(1))
    rid = revision['revision_id']
    trips = revision['problem']['trips']
    pair = next((a,b) for a in trips for b in trips if a['id'] != b['id']
                and a['start_minutes'] < b['end_minutes'] and b['start_minutes'] < a['end_minutes'])
    resource = revision['problem']['resources'][0]['resource_id']
    response = client.post(f'/api/v1/scheduling/revisions/{rid}/patches', headers=auth(1), json={
        'version': revision['version'], 'patches': [
            {'trip_id': t['id'], 'new_resource_id': resource, 'is_locked': False} for t in pair]})
    assert response.status_code == 200, response.text
    updated = response.json()
    assert not updated['verification']['valid']
    assert 'RULE_NO_TEMPORAL_OVERLAP' in [v['rule_id'] for v in updated['verification']['violations']]
    assert client.post(f'/api/v1/scheduling/revisions/{rid}/publish', headers=auth(1),
                       json={'version': updated['version']}).status_code == 422
    assert client.get('/api/v1/scheduling/revisions/active?source_kind=reference_archive', headers=auth(1)).json()['status'] == 'draft'


def test_unknown_ids_rejected_and_locked_move_atomic(setup):
    client, auth = setup
    revision = initialize(client, auth(1))
    rid = revision['revision_id']
    row = revision['assignments'][0]
    url = f'/api/v1/scheduling/revisions/{rid}/patches'
    for trip, resource in [('missing', row['resource_id']), (row['trip_id'], 'missing')]:
        assert client.post(url, headers=auth(1), json={'version': revision['version'], 'patches': [
            {'trip_id': trip, 'new_resource_id': resource}]}).status_code == 422
    locked = client.post(url, headers=auth(1), json={'version': revision['version'], 'patches': [
        {'trip_id': row['trip_id'], 'new_resource_id': row['resource_id'], 'is_locked': True}]}).json()
    other = next(r['resource_id'] for r in revision['problem']['resources'] if r['resource_id'] != row['resource_id'])
    assert client.post(url, headers=auth(1), json={'version': locked['version'], 'patches': [
        {'trip_id': row['trip_id'], 'new_resource_id': other, 'is_locked': False}]}).status_code == 409
    loaded = client.get('/api/v1/scheduling/revisions/active?source_kind=reference_archive', headers=auth(1)).json()
    assert loaded == locked


def test_authenticated_identity_reflects_persisted_permissions(setup):
    client, auth = setup
    for uid, admin in [(1, True), (3, False)]:
        response = client.get('/auth/me', headers=auth(uid))
        assert response.status_code == 200
        assert response.json()['is_admin'] is admin
        assert response.json()['ktel_id'] == 1


def test_cv_submission_requires_existing_owned_snapshot_and_permission(setup):
    client, auth = setup
    revision = initialize(client, auth(1))
    for uid, snapshot, expected in [(1,'missing',404),(2,revision['revision_id'],404),(3,revision['revision_id'],403)]:
        response=client.post('/optimization/runs',headers=auth(uid),json={'snapshot_id':snapshot})
        assert response.status_code==expected
    assert client.post('/optimization/runs',headers=auth(1),json={
        'snapshot_id':revision['revision_id'],'config':{'iterations':0}}).status_code==422
