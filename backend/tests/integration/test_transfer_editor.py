"""Saved travel durations stay inspectable, complete and safe to edit."""
from tests.integration.test_identity import identity_setup,accept
from tests.integration.test_canonical_studio import prepared_customer

URL='/api/v1/transfers/editor'


def editor(client,headers,**parameters):
    response=client.get(URL,headers=headers,params={'service_date':'2026-06-01',**parameters})
    assert response.status_code==200,response.text[:500]
    return response.json()


def change(direction,minutes):
    return {key:direction[key] for key in ('origin_station_id','destination_station_id','origin_version','destination_version')}|{'expected_version':direction['version'],'minutes':minutes}


def test_saved_directions_remain_visible_and_a_single_edit_preserves_the_reverse(identity_setup):
    client,headers,template,pairing,driver=prepared_customer(identity_setup)
    revision=client.post('/api/v1/scheduling/revisions',headers=headers,json={'service_date':'2026-06-01'}).json()
    data=editor(client,headers)
    assert data['total']==1 and data['counts']=={'required_directions':2,'saved_directions':2,'missing_directions':0,'review_directions':0}
    pair=data['items'][0]
    assert (pair['forward']['minutes'],pair['reverse']['minutes'])==(30,35)
    saved=client.post(URL,headers=headers,json={'items':[change(pair['forward'],42)]})
    assert saved.status_code==200,saved.text[:500]
    pair=editor(client,headers)['items'][0]
    assert (pair['forward']['minutes'],pair['reverse']['minutes'])==(42,35)
    assert pair['forward']['version']==2 and pair['reverse']['version']==1
    assert client.get('/api/v1/scheduling/revisions/'+revision['revision_id'],headers=headers).json()['source_review_required'] is True


def test_missing_editor_paginates_beyond_the_readiness_sample_without_inventing_minutes(identity_setup):
    from tests.integration.test_operational_snapshots import template_payload
    client,headers,template,pairing,driver=prepared_customer(identity_setup)
    origin=template['origin']
    for index in range(10):
        station=client.post('/api/v1/stations',headers=headers,json={'code':'EX'+str(index),'name_el':'Σταθμός '+str(index)}).json()
        response=client.post('/api/v1/timetables',headers=headers,json=template_payload(origin,station,trip_code='EX'+str(index)))
        assert response.status_code==201,response.text[:500]
    readiness=client.get('/api/v1/setup/readiness?service_date=2026-06-01',headers=headers).json()
    assert len(readiness['missing_transfers'])==100 and readiness['missing_transfer_count']==130
    keys=set()
    for page in (1,2,3):
        data=editor(client,headers,filter='missing',page=page)
        assert data['total']==65 and data['counts']['required_directions']==132
        assert data['counts']['missing_directions']==130
        for pair in data['items']:
            assert pair['key'] not in keys;keys.add(pair['key'])
            assert pair['forward']['minutes'] is None and pair['reverse']['minutes'] is None
    assert len(keys)==65


def test_multi_direction_edit_rolls_back_on_a_stale_station_or_record(identity_setup):
    client,headers,template,pairing,driver=prepared_customer(identity_setup)
    pair=editor(client,headers)['items'][0]
    first,second=change(pair['forward'],44),change(pair['reverse'],46)
    second['expected_version']=99
    rejected=client.post(URL,headers=headers,json={'items':[first,second]})
    assert rejected.status_code==409,rejected.text[:500]
    current=editor(client,headers)['items'][0]
    assert (current['forward']['minutes'],current['reverse']['minutes'])==(30,35)
    assert client.patch('/api/v1/stations/'+str(template['origin']['id']),headers=headers,json={'version':1,'latitude':38.3}).status_code==200
    rejected=client.post(URL,headers=headers,json={'items':[first]})
    assert rejected.status_code==409 and rejected.json()['detail']['code']=='source_changed'
    assert editor(client,headers)['items'][0]['forward']['minutes']==30


def test_confirming_one_stale_direction_does_not_confirm_its_reverse(identity_setup):
    client,headers,template,pairing,driver=prepared_customer(identity_setup)
    assert client.patch('/api/v1/stations/'+str(template['origin']['id']),headers=headers,json={'version':1,'latitude':38.3}).status_code==200
    data=editor(client,headers)
    assert data['counts']['review_directions']==2
    forward=data['items'][0]['forward']
    response=client.post(URL,headers=headers,json={'items':[change(forward,30)]})
    assert response.status_code==200,response.text[:500]
    pair=editor(client,headers)['items'][0]
    assert pair['forward']['needs_review'] is False and pair['reverse']['needs_review'] is True


def test_transfer_editor_respects_foreign_tenants_and_read_only_members(identity_setup):
    from app.domain.identity.service import issue_invitation
    client,headers,template,pairing,driver=prepared_customer(identity_setup)
    direction=editor(client,headers)['items'][0]['forward']
    foreign={'Authorization':'Bearer '+accept(client,identity_setup['second']).json()['access_token']}
    assert editor(client,foreign)['total']==0
    assert client.post(URL,headers=foreign,json={'items':[change(direction,40)]}).status_code==422
    with identity_setup['owner_factory']() as db:
        invitation=issue_invitation(db,identity_setup['first'].tenant_id,'transfer-reader@example.org','viewer');db.commit()
    reader={'Authorization':'Bearer '+accept(client,invitation).json()['access_token']}
    assert editor(client,reader)['total']==1
    assert client.post(URL,headers=reader,json={'items':[change(direction,40)]}).status_code==403


def test_empty_values_and_duplicate_directions_cannot_silently_become_a_transfer(identity_setup):
    client,headers,template,pairing,driver=prepared_customer(identity_setup)
    direction=editor(client,headers)['items'][0]['forward']
    update=change(direction,40)
    for items in ([{**update,'minutes':None}],[update,update],[{**update,'minutes':True}]):
        response=client.post(URL,headers=headers,json={'items':items})
        assert response.status_code==422,response.text[:500]
    assert editor(client,headers)['items'][0]['forward']['minutes']==30
