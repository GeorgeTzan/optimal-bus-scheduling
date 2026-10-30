from datetime import date
from dataclasses import replace
from tests.api.test_scheduling import setup, initialize
from db.database import get_db
from main import app
from app.domain.scheduling.snapshots import RevisionSnapshot
from app.domain.scheduling.models import RevisionAssignment


def test_verified_approval_publish_and_immutable_version(setup):
    client, auth=setup
    rev=initialize(client,auth(1));rid=rev['revision_id']
    # Isolate a known valid single-trip problem through the fixture DB, never a public API.
    generator=app.dependency_overrides[get_db]();db=next(generator)
    snap=db.query(RevisionSnapshot).filter_by(revision_id=rid).one()
    problem=dict(snap.problem_data);trip=problem['trips'][0]
    problem['trips']=[trip];problem['chains']=[]
    snap.problem_data=problem
    db.query(RevisionAssignment).filter(RevisionAssignment.revision_id==rid,RevisionAssignment.trip_id!=trip['id']).delete()
    row=db.query(RevisionAssignment).filter_by(revision_id=rid).one();resource_id=problem['resources'][0]['resource_id'];row.resource_id=resource_id
    db.commit();generator.close()
    prefix=f'/api/v1/scheduling/revisions/{rid}'
    assert client.post(prefix+'/publish',headers=auth(1),json={'version':1}).status_code==409
    requested=client.post(prefix+'/request-approval',headers=auth(1),json={'version':1})
    assert requested.status_code==200,requested.text
    approved=client.post(prefix+'/approve',headers=auth(1),json={'version':2})
    assert approved.status_code==200,approved.text
    edited=client.post(prefix+'/patches',headers=auth(1),json={'version':3,'patches':[
        {'trip_id':trip['id'],'new_resource_id':resource_id,'is_locked':True}]})
    assert edited.status_code==200
    assert edited.json()['status']=='draft'
    assert client.post(prefix+'/publish',headers=auth(1),json={'version':4}).status_code==409
    for action,version in [('request-approval',4),('approve',5),('publish',6)]:
        response=client.post(prefix+'/'+action,headers=auth(1),json={'version':version})
        assert response.status_code==200,response.text
    assert response.json()['status']=='published'
    assert client.post(prefix+'/patches',headers=auth(1),json={'version':7,'patches':[
        {'trip_id':trip['id'],'new_resource_id':resource_id,'is_locked':False}]}).status_code==409
