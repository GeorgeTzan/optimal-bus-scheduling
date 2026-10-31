"""Flush-only reporting services. Publication rows and assignments are never mutated."""
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import func
from db.models import KTEL
from app.domain.events.outbox import OutboxEvent
from app.domain.scheduling.models import Publication,RevisionAssignment,ScheduleRevision
from app.domain.scheduling.snapshots import RevisionSnapshot,display_metadata
from .operations_models import OperationalTripState,OperationalEvent

OPEN_KINDS=('delay','breakdown','note')


def event_view(event):
    return {key:getattr(event,key) for key in ('id','kind','description','delay_minutes','actor_id','actor_name','recorded_at','resolved_event_id','state_version')}


class Operations:
    def __init__(self,db,user):
        self.db,self.user,self.tenant=db,user,user.ktel_id

    def query(self,model):return self.db.query(model).filter_by(tenant_id=self.tenant)

    def publication(self,identifier):
        row=self.query(Publication).filter_by(publication_id=identifier).first()
        snapshot=self.query(RevisionSnapshot).filter_by(revision_id=row.revision_id).first() if row else None
        if not snapshot or snapshot.source_data.get('source')!='operational':
            raise HTTPException(404,'Published schedule not found in your workspace.')
        return row,snapshot

    def lock(self):
        self.db.query(KTEL).filter_by(id=self.tenant).populate_existing().with_for_update().one()

    def linked_history(self,publication,assignments,publications):
        # Follow only this revision's verified ancestry, never merely the same date.
        revision=self.query(ScheduleRevision).filter_by(revision_id=publication.revision_id).first()
        ancestry=[];seen=set()
        while revision and revision.parent_revision_id:
            parent=revision.parent_revision_id
            if parent in seen or len(seen)>=1000:raise HTTPException(409,'Schedule history requires review.')
            seen.add(parent);ancestry.append(parent)
            revision=self.query(ScheduleRevision).filter_by(revision_id=parent).first()
        old_publications={row.publication_id:row for row in publications if row.revision_id in ancestry}
        if not old_publications:return {},{}
        current={row.trip_id:row for row in assignments}
        old_rows=self.query(RevisionAssignment).filter(RevisionAssignment.revision_id.in_(ancestry),RevisionAssignment.trip_id.in_(current)).all()
        def facts(row):return (row.trip_id,row.start_minutes,row.end_minutes,row.start_station,row.end_station)
        matching={(row.revision_id,row.trip_id) for row in old_rows if row.trip_id in current and facts(row)==facts(current[row.trip_id])}
        states=[state for state in self.query(OperationalTripState).filter(OperationalTripState.publication_id.in_(old_publications),OperationalTripState.trip_id.in_(current)).all()
            if (state.revision_id,state.trip_id) in matching and old_publications[state.publication_id].revision_id==state.revision_id]
        if not states:return {},{}
        state_map={state.id:state for state in states}
        events=self.query(OperationalEvent).filter(OperationalEvent.state_id.in_(state_map)).order_by(OperationalEvent.id).all()
        resolved={event.resolved_event_id for event in events if event.resolved_event_id is not None}
        linked={};counts={}
        for event in events:
            state=state_map[event.state_id];source=old_publications[state.publication_id]
            is_open=event.kind in OPEN_KINDS and event.id not in resolved
            if is_open:counts[state.trip_id]=counts.get(state.trip_id,0)+1
            linked.setdefault(state.trip_id,[]).append({**event_view(event),'source_state_version':state.version,'is_open':is_open,
                'source_publication':{'publication_id':source.publication_id,'revision_id':source.revision_id,
                    'published_at':source.published_at.replace(tzinfo=timezone.utc),'published_by':source.published_by}})
        return linked,counts

    def day(self,service_date=None,publication_id=None,q='',open_only=False,page=1,page_size=25,trip_id=None):
        tenant=self.db.query(KTEL).filter_by(id=self.tenant).one()
        service_date=service_date or datetime.now(ZoneInfo(tenant.timezone)).date()
        publications=(self.query(Publication).join(RevisionSnapshot,(Publication.revision_id==RevisionSnapshot.revision_id)&(Publication.tenant_id==RevisionSnapshot.tenant_id))
            .filter(RevisionSnapshot.source_data['source'].as_string()=='operational',RevisionSnapshot.problem_data['service_date'].as_string()==service_date.isoformat())
            .order_by(Publication.published_at.desc(),Publication.id.desc()).all())
        choices=[{'publication_id':row.publication_id,'revision_id':row.revision_id,'published_at':row.published_at.replace(tzinfo=timezone.utc),'published_by':row.published_by} for row in publications]
        selected=next((row for row in publications if row.publication_id==publication_id),None) if publication_id else (publications[0] if publications else None)
        if publication_id and selected is None:raise HTTPException(404,'Publication not found for this day in your workspace.')
        result={'service_date':service_date.isoformat(),'timezone':tenant.timezone,'publications':choices,'publication':next((item for item in choices if selected and item['publication_id']==selected.publication_id),None),
                'newer_publication':bool(selected and selected.id!=publications[0].id),'items':[],'total':0,'open_count':0,'page':page,'page_size':page_size}
        if selected is None:return result
        _,snapshot=self.publication(selected.publication_id)
        result.update(display_metadata(snapshot))
        source=snapshot.source_data
        trips={row['id']:row for row in source['trips']}
        resources={row['resource_id']:row for row in source['resources']}
        states=self.query(OperationalTripState).filter_by(publication_id=selected.publication_id).all()
        state_by_trip={row.trip_id:row for row in states}
        # Open counts cover the entire publication independently of search/page.
        resolutions=self.query(OperationalEvent).filter(OperationalEvent.resolved_event_id.is_not(None)).with_entities(OperationalEvent.resolved_event_id)
        counts=dict(self.query(OperationalEvent).join(OperationalTripState,(OperationalEvent.state_id==OperationalTripState.id)&(OperationalEvent.tenant_id==OperationalTripState.tenant_id))
            .filter(OperationalTripState.publication_id==selected.publication_id,OperationalEvent.kind.in_(OPEN_KINDS),~OperationalEvent.id.in_(resolutions))
            .with_entities(OperationalEvent.state_id,func.count(OperationalEvent.id)).group_by(OperationalEvent.state_id).all())
        assignments=self.query(RevisionAssignment).filter_by(revision_id=selected.revision_id).order_by(RevisionAssignment.start_minutes,RevisionAssignment.trip_id).all()
        linked,linked_counts=self.linked_history(selected,assignments,publications)
        result['open_count']=sum(counts.values())+sum(linked_counts.values())
        query=q.casefold().strip()
        filtered=[]
        for row in assignments:
            if trip_id is not None and row.trip_id != trip_id:continue
            state=state_by_trip.get(row.trip_id)
            if open_only and not counts.get(state.id if state else None,0) and not linked_counts.get(row.trip_id,0):continue
            trip,resource=trips.get(row.trip_id,{}),resources.get(row.resource_id,{})
            searchable=[trip.get('trip_code',''),resource.get('driver_name',''),resource.get('driver_code',''),resource.get('vehicle_label',''),resource.get('vehicle_code','')]
            searchable += [str(trip.get(end,{}).get(key,'')) for end in ('origin','destination') for key in ('code','name_el','name_en')]
            if query and not any(query in str(value).casefold() for value in searchable):continue
            filtered.append(row)
        result['total']=len(filtered)
        chosen=filtered[(page-1)*page_size:page*page_size]
        chosen_ids=[state_by_trip[row.trip_id].id for row in chosen if row.trip_id in state_by_trip]
        events=self.query(OperationalEvent).filter(OperationalEvent.state_id.in_(chosen_ids)).order_by(OperationalEvent.id).all() if chosen_ids else []
        histories={}
        for event in events:histories.setdefault(event.state_id,[]).append(event)
        for row in chosen:
            state=state_by_trip.get(row.trip_id);history=histories.get(state.id,[]) if state else []
            explicit=[event for event in history if event.kind in ('departure','completion')]
            result['items'].append({'trip_id':row.trip_id,'trip':trips.get(row.trip_id,{}),'resource':resources.get(row.resource_id),
                'start_minutes':row.start_minutes,'end_minutes':row.end_minutes,'is_cancelled':row.is_cancelled,'cancellation_reason':row.cancellation_reason,'version':state.version if state else 0,
                'reported_status':explicit[-1].kind if explicit else 'planned','open_count':counts.get(state.id,0) if state else 0,
                'events':[event_view(event) for event in history],'linked_events':linked.get(row.trip_id,[]),'linked_open_count':linked_counts.get(row.trip_id,0)})
        return result

    def retry(self,request,digest):
        event=self.query(OperationalEvent).filter_by(request_id=str(request.request_id)).first()
        if event:
            if event.payload_hash!=digest:raise HTTPException(409,{'code':'request_changed','message':'This request was already used with different details. Review before sending a new report.'})
            return event

    def record(self,request,target_id=None):
        self.lock()
        payload={'request':request.model_dump(mode='json'),'target_id':target_id,'actor_id':self.user.id}
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        previous=self.retry(request,digest)
        if previous:return event_view(previous)
        target=None
        if target_id is not None:
            target=self.query(OperationalEvent).filter_by(id=target_id).first()
            if target is None:raise HTTPException(404,'Report not found in your workspace.')
            state=self.query(OperationalTripState).filter_by(id=target.state_id).populate_existing().with_for_update().one()
            self.publication(state.publication_id)
        else:
            publication,_=self.publication(request.publication_id)
            assignment=self.query(RevisionAssignment).filter_by(revision_id=publication.revision_id,trip_id=request.trip_id).first()
            if assignment is None:raise HTTPException(404,'Trip not found in this published schedule.')
            state=self.query(OperationalTripState).filter_by(publication_id=publication.publication_id,trip_id=request.trip_id).populate_existing().with_for_update().first()
        version=state.version if state else 0
        if request.expected_version!=version:raise HTTPException(409,{'code':'state_changed','message':'Another update was recorded. Refresh the trip and review your report before sending again.','version':version})
        if target:
            if target.kind not in OPEN_KINDS or self.query(OperationalEvent).filter_by(resolved_event_id=target.id).first():
                raise HTTPException(409,{'code':'already_resolved','message':'This report is already resolved or does not need resolution.'})
        if state is None:
            state=OperationalTripState(tenant_id=self.tenant,publication_id=publication.publication_id,revision_id=publication.revision_id,trip_id=request.trip_id,version=1)
            self.db.add(state)
        else:state.version+=1
        self.db.flush()
        event=OperationalEvent(tenant_id=self.tenant,state_id=state.id,kind='resolution' if target else request.kind,
            description=request.note if target else request.description,delay_minutes=None if target else request.delay_minutes,
            actor_id=self.user.id,actor_name=self.user.full_name or self.user.email,recorded_at=datetime.now(timezone.utc),
            resolved_event_id=target.id if target else None,request_id=str(request.request_id),payload_hash=digest,state_version=state.version)
        self.db.add(event)
        self.db.add(OutboxEvent(tenant_id=self.tenant,event_type='operations.updated',job_id=None,
            payload={'publication_id':state.publication_id,'trip_id':state.trip_id,'version':state.version}))
        self.db.flush()
        return event_view(event)
