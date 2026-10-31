"""Prior reports remain attributed to the publication where they were recorded."""
import uuid
from tests.integration.test_identity import identity_setup,accept
from tests.integration.test_daily_operations import board,report_payload
from tests.integration.test_schedule_changes import APPLY,transition
from tests.integration.test_schedule_change_actions import customer_with_two_confirmed_crews


def test_prior_reports_and_actual_departure_remain_visible_and_resolvable_after_successor(identity_setup):
    client,headers,revision,first,other=customer_with_two_confirmed_crews(identity_setup)
    before=board(client,headers);original=before['publication']['publication_id'];trip=before['items'][0]['trip_id']
    delay=client.post('/api/v1/operations/reports',headers=headers,json=report_payload(before,description='Roadworks reported.'))
    assert delay.status_code==201,delay.text[:400]
    departure=client.post('/api/v1/operations/reports',headers=headers,json=report_payload(before,expected_version=1,kind='departure',delay_minutes=None,description='Driver confirmed departure.'))
    assert departure.status_code==201,departure.text[:400]
    later=before['items'][1]['trip_id']
    request={'publication_id':original,'version':revision['version'],'reason':'Reassign later work.',
        'reviewed_not_started':[later],'patches':[{'trip_id':later,'new_resource_id':'UNASSIGNED'}],'request_id':str(uuid.uuid4())}
    response=client.post(APPLY,headers=headers,json=request);assert response.status_code==201,response.text[:400];successor=response.json()
    for action in ('request-approval','approve','publish'):
        response=transition(client,headers,successor,action);assert response.status_code==200,response.text[:400];successor=response.json()
    latest=board(client,headers);item=next(item for item in latest['items'] if item['trip_id']==trip)
    assert latest['open_count']==1 and item['linked_open_count']==1
    assert board(client,headers,open_only=True)['total']==1
    assert board(client,headers,q='no-such-trip')['open_count']==1
    assert [event['kind'] for event in item['linked_events']]==['delay','departure']
    assert all(event['source_publication']['publication_id']==original and event['source_state_version']==2 for event in item['linked_events'])
    assert item['linked_events'][0]['actor_name']=='KTEL administrator'
    # Resolution updates only the original state; the latest board reflects it through its link.
    response=client.post('/api/v1/operations/reports/'+str(delay.json()['id'])+'/resolve',headers=headers,json={
        'expected_version':2,'request_id':str(uuid.uuid4()),'note':'Traffic cleared.'})
    assert response.status_code==201,response.text[:400]
    latest=board(client,headers);item=next(item for item in latest['items'] if item['trip_id']==trip)
    assert latest['open_count']==0 and item['linked_open_count']==0
    assert [event['kind'] for event in item['linked_events']]==['delay','departure','resolution']
    assert board(client,headers,publication_id=original)['items'][0]['events'][0]['description']=='Roadworks reported.'
    foreign={'Authorization':'Bearer '+accept(client,identity_setup['second']).json()['access_token']}
    assert board(client,foreign)['publication'] is None
    assert client.post('/api/v1/operations/reports/'+str(delay.json()['id'])+'/resolve',headers=foreign,json={
        'expected_version':3,'request_id':str(uuid.uuid4()),'note':'Wrong organization'}).status_code==404


def test_changed_trip_times_do_not_link_an_ambiguous_earlier_report(identity_setup):
    from tests.integration.test_daily_operations import published_customer,publish_revision
    client,headers,revision=published_customer(identity_setup);before=board(client,headers)
    assert client.post('/api/v1/operations/reports',headers=headers,json=report_payload(before)).status_code==201
    source=revision['source_trips'][0]
    response=client.patch('/api/v1/timetables/'+str(source['template_id']),headers=headers,json={'version':source['template_version'],'departure_time':'08:15'})
    assert response.status_code==200,response.text[:400]
    successor=publish_revision(client,headers)
    assert successor['revision_id']!=revision['revision_id']
    latest=board(client,headers)
    assert latest['items'][0]['linked_events']==[] and latest['open_count']==0
    assert board(client,headers,publication_id=before['publication']['publication_id'])['open_count']==1


def test_prior_open_report_remains_linked_to_a_cancelled_trip(identity_setup):
    from tests.integration.test_daily_operations import published_customer
    client,headers,revision=published_customer(identity_setup);before=board(client,headers)
    assert client.post('/api/v1/operations/reports',headers=headers,json=report_payload(before)).status_code==201
    trip=before['items'][0]['trip_id']
    request={'publication_id':before['publication']['publication_id'],'version':revision['version'],'reason':'Trip cannot run.',
        'reviewed_not_started':[trip],'patches':[{'trip_id':trip,'operation':'cancel','reason':'Vehicle unavailable.'}],'request_id':str(uuid.uuid4())}
    response=client.post(APPLY,headers=headers,json=request);assert response.status_code==201,response.text[:400];successor=response.json()
    for action in ('request-approval','approve','publish'):
        response=transition(client,headers,successor,action);assert response.status_code==200,response.text[:400];successor=response.json()
    item=board(client,headers)['items'][0]
    assert item['is_cancelled'] and item['linked_open_count']==1 and item['linked_events'][0]['source_publication']['publication_id']==before['publication']['publication_id']
