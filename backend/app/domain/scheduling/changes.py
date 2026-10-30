"""Create a reviewed draft successor without changing published assignments."""
import copy
import hashlib
import json
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from db.models import KTEL
from app.api.scheduling import serialize
from app.domain.incidents.operations_models import OperationalEvent,OperationalTripState
from app.domain.optimization.availability import availability_allows_trip
from app.domain.optimization.contracts import Assignment,ChainSnapshot,ResourceSnapshot
from app.domain.scheduling.change_models import ScheduleChange,RevisionCrew
from app.domain.scheduling.models import Publication,RevisionAssignment,ScheduleRevision,SchedulingAuditLog
from app.domain.scheduling.snapshots import RevisionSnapshot,decode_problem,encode_problem
from app.domain.scheduling.source_review import source_review_required
from app.domain.verification.verifier import HardRuleVerifier


class ScheduleChanges:
    def __init__(self,db,user):self.db,self.user,self.tenant=db,user,user.ktel_id
    def query(self,model):return self.db.query(model).filter_by(tenant_id=self.tenant)

    def base(self,request,lock=False):
        publication=self.query(Publication).filter_by(publication_id=request.publication_id).first()
        if publication is None:raise HTTPException(404,'Publication not found in your workspace.')
        query=self.query(ScheduleRevision).filter_by(revision_id=publication.revision_id)
        revision=query.populate_existing().with_for_update().first() if lock else query.first()
        snapshot=self.query(RevisionSnapshot).filter_by(revision_id=publication.revision_id).first()
        if revision is None or snapshot is None or snapshot.source_data.get('source')!='operational':
            raise HTTPException(404,'Operational publication not found in your workspace.')
        if revision.version!=request.version or revision.status!='published':
            raise HTTPException(409,{'code':'base_changed','message':'The published schedule changed. Review it again.'})
        return publication,revision,snapshot

    def refreshed(self,snapshot,problem,extra):
        """Current usable windows for every resource, including any new replacement crew. The published source is never touched."""
        from app.domain.office.availability import availability_for_resources
        from app.domain.timetables.operations import fingerprint
        from app.domain.scheduling.availability_review import frozen_horizon
        origin,end=frozen_horizon(snapshot.source_data,problem)
        resources=tuple(problem.resources)+tuple(extra);keys=[(int(item.driver_id),int(item.bus_id)) for item in resources]
        found=availability_for_resources(self.db,self.tenant,keys,origin,end)
        minutes=lambda moment:int((moment-origin).total_seconds()//60)
        fresh=tuple(replace(item,available_windows=None if found[key].windows is None else tuple((minutes(a),minutes(b)) for a,b in found[key].windows)) for item,key in zip(resources,keys))
        availability={'fingerprint':fingerprint([found[key].fingerprint for key in keys]),'start_utc':origin.isoformat(),'end_utc':end.isoformat(),
            'resources':{item.resource_id:{'windows':[list(window) for window in (item.available_windows or ())] if item.available_windows is not None else None,
                'fingerprint':found[key].fingerprint,'warnings':list(found[key].warnings),'findings':list(found[key].findings)} for item,key in zip(fresh,keys)}}
        return fresh,availability

    def validate(self,request,publication,revision,snapshot):
        date=snapshot.problem_data['service_date']
        latest=(self.query(Publication).join(RevisionSnapshot,(Publication.tenant_id==RevisionSnapshot.tenant_id)&(Publication.revision_id==RevisionSnapshot.revision_id))
            .filter(RevisionSnapshot.problem_data['service_date'].as_string()==date,RevisionSnapshot.source_data['source'].as_string()=='operational')
            .order_by(Publication.published_at.desc(),Publication.id.desc()).first())
        if latest is None or latest.publication_id!=publication.publication_id:
            raise HTTPException(409,{'code':'newer_publication','message':'A newer schedule was published. Review that version.'})
        if source_review_required(self.db,SimpleNamespace(tenant_id=self.tenant,status='draft'),snapshot):
            raise HTTPException(409,{'code':'source_changed','message':'The day\'s source records changed. Review the service day first.'})
        problem=decode_problem(snapshot.problem_data)
        resource_map={item.resource_id:item for item in problem.resources}
        labels={item['resource_id']:item for item in snapshot.source_data.get('resources',[])}
        resources=set(resource_map)|{'UNASSIGNED'}
        created_crews={}
        rows=self.query(RevisionAssignment).filter_by(revision_id=revision.revision_id).order_by(RevisionAssignment.trip_id).all()
        by_trip={row.trip_id:row for row in rows}
        # Follow revision ancestry; explicit reports remain attached to their original publication.
        lineage=[];current=revision;seen=set()
        while current is not None:
            if current.revision_id in seen or len(seen)>=1000:raise HTTPException(409,'Schedule history requires review.')
            seen.add(current.revision_id);lineage.append(current.revision_id)
            current=self.query(ScheduleRevision).filter_by(revision_id=current.parent_revision_id).first() if current.parent_revision_id else None
        operated={trip for (trip,) in (self.query(OperationalEvent).join(OperationalTripState,(OperationalEvent.tenant_id==OperationalTripState.tenant_id)&(OperationalEvent.state_id==OperationalTripState.id))
            .filter(OperationalTripState.revision_id.in_(lineage),OperationalEvent.kind.in_(('departure','completion')))
            .with_entities(OperationalTripState.trip_id).all())}
        changes=[];chosen={};cancelled={};unlocked=set()
        current={item.resource_id:item for item in self.refreshed(snapshot,problem,())[0]};trip_facts={trip.id:trip for trip in problem.trips}
        for patch in request.patches:
            row=by_trip.get(patch.trip_id)
            if row is None:raise HTTPException(422,'Unknown trip in this publication.')
            if row.is_cancelled:raise HTTPException(409,{'code':'cancelled_trip','message':'This service is already cancelled.'})
            replacement_details={}
            if patch.operation=='replace_driver':
                original=resource_map.get(row.resource_id);replacement=resource_map.get(patch.replacement_resource_id)
                old_label=labels.get(row.resource_id);new_label=labels.get(patch.replacement_resource_id)
                if not original or not replacement or not old_label or not new_label:
                    raise HTTPException(422,'Choose an existing confirmed crew and assigned trip.')
                if original.driver_id==replacement.driver_id:
                    raise HTTPException(422,'Choose a different driver.')
                if new_label.get('driver_version')!=patch.driver_version or old_label.get('vehicle_version')!=patch.vehicle_version:
                    raise HTTPException(409,{'code':'source_changed','message':'The driver or vehicle changed. Review current records.'})
                try:driver_id=int(replacement.driver_id);vehicle_id=int(original.bus_id)
                except (TypeError,ValueError):raise HTTPException(422,'Driver and vehicle identities require review.')
                identity=f'{self.tenant}:{revision.revision_id}:{driver_id}:{vehicle_id}'
                destination='CREW_'+hashlib.sha256(identity.encode()).hexdigest()[:24]
                resource=ResourceSnapshot(destination,replacement.driver_id,original.bus_id,original.home_station,original.bus_type)
                label={**old_label,'resource_id':destination,'driver_id':driver_id,'driver_name':new_label['driver_name'],
                    'driver_code':new_label['driver_code'],'driver_version':patch.driver_version,'vehicle_version':patch.vehicle_version}
                created_crews[destination]=(resource,label,driver_id,vehicle_id,patch.driver_version,patch.vehicle_version)
                resources.add(destination)
                replacement_details={'replacement_resource_id':patch.replacement_resource_id,'driver_version':patch.driver_version,
                    'vehicle_version':patch.vehicle_version,'confirm_replacement':True}
            else:
                destination='UNASSIGNED' if patch.operation in ('unassign','cancel') else patch.new_resource_id
            if destination not in resources:raise HTTPException(422,'Unknown resource in this publication.')
            if patch.operation!='cancel' and row.resource_id==destination:raise HTTPException(422,'Choose a different assignment.')
            if row.is_locked:
                crew=current.get(row.resource_id);fact=trip_facts.get(row.trip_id)
                conflict=patch.unlock and crew is not None and fact is not None and (crew.available_windows is None or not availability_allows_trip(crew,fact))
                if not conflict:
                    raise HTTPException(409,{'code':'unlock_without_conflict' if patch.unlock else 'locked_trip','message':'This lock can only be released when its driver or vehicle is unavailable for the trip.' if patch.unlock else 'This assignment is locked. Review the lock before changing it.'})
                unlocked.add(row.trip_id)
            if row.trip_id in operated:raise HTTPException(409,{'code':'operated_trip','message':'This trip has a reported departure or completion and cannot be changed here.'})
            chosen[row.trip_id]=destination
            if patch.operation=='cancel':cancelled[row.trip_id]=patch.reason
            changes.append({'trip_id':row.trip_id,'operation':patch.operation,'reason':patch.reason,**replacement_details,**({'unlocked':True} if row.trip_id in unlocked else {}),
                'original_resource_id':row.resource_id,'new_resource_id':destination,
                'start_minutes':row.start_minutes,'end_minutes':row.end_minutes,'start_station':row.start_station,'end_station':row.end_station})
        excluded=set(cancelled)
        fresh,availability=self.refreshed(snapshot,problem,tuple(item[0] for item in created_crews.values() if item[0].resource_id not in resource_map))
        active_problem=replace(problem,resources=fresh,trips=tuple(trip for trip in problem.trips if trip.id not in excluded),
            chains=tuple(ChainSnapshot(remaining) for chain in problem.chains
                         if (remaining:=tuple(trip for trip in chain.trip_ids if trip not in excluded))),
            availability_enforced=True,availability_exempt_trip_ids=tuple(sorted(operated)))
        proposed=[Assignment(chosen.get(row.trip_id,row.resource_id),row.trip_id,row.start_minutes,row.end_minutes,row.start_station,row.end_station)
                  for row in rows if not row.is_cancelled and row.trip_id not in excluded and chosen.get(row.trip_id,row.resource_id)!='UNASSIGNED']
        report=HardRuleVerifier().verify(active_problem,proposed)
        return rows,chosen,created_crews,{'publication_id':publication.publication_id,'base_revision_id':revision.revision_id,'version':revision.version,
            'source_versions':snapshot.source_data.get('source_versions',{}),'changes':changes,'verification':asdict(report)},(fresh,availability,tuple(sorted(operated)),unlocked)

    def preview(self,request):
        publication,revision,snapshot=self.base(request)
        return self.validate(request,publication,revision,snapshot)[3]

    def create(self,request):
        # The established mutation order is revision row followed by organization row.
        publication,revision,snapshot=self.base(request,lock=True)
        self.db.query(KTEL).filter_by(id=self.tenant).populate_existing().with_for_update().one()
        digest=hashlib.sha256(json.dumps({'request':request.model_dump(mode='json'),'actor':self.user.id},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        previous=self.query(ScheduleChange).filter_by(request_id=str(request.request_id)).first()
        if previous:
            if previous.payload_hash!=digest:raise HTTPException(409,{'code':'request_changed','message':'This request was already used with different details.'})
            return previous.response_data
        rows,chosen,created_crews,preview,(fresh,availability,exempt,unlocked)=self.validate(request,publication,revision,snapshot)
        if not preview['verification']['valid']:
            raise HTTPException(422,{'code':'verification_failed','message':'Resolve the reported conflicts before saving this change.','verification':preview['verification']})
        identifier=str(uuid4())
        successor=ScheduleRevision(tenant_id=self.tenant,revision_id=identifier,period_id=revision.period_id,parent_revision_id=revision.revision_id,
            version=1,status='draft',author=str(self.user.id),comment=request.reason,created_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc))
        self.db.add(successor);self.db.flush()
        cancelled={item['trip_id']:item['reason'] for item in preview['changes'] if item['operation']=='cancel'}
        base_problem=decode_problem(snapshot.problem_data)
        new_problem=replace(base_problem,problem_id=identifier,resources=fresh,trips=tuple(trip for trip in base_problem.trips if trip.id not in cancelled),
            chains=tuple(ChainSnapshot(remaining) for chain in base_problem.chains
                         if (remaining:=tuple(trip for trip in chain.trip_ids if trip not in cancelled))),
            availability_enforced=True,availability_exempt_trip_ids=exempt)
        source_data=copy.deepcopy(snapshot.source_data);source_data['availability']=availability;source_data['source_schema_version']='ktel-operational-v2'
        for source_trip in source_data.get('trips',[]):
            if source_trip['id'] in cancelled:
                source_trip['is_cancelled']=True;source_trip['cancellation_reason']=cancelled[source_trip['id']]
        known_labels={item['resource_id'] for item in source_data.get('resources',[])}
        source_data.setdefault('resources',[]).extend(item[1] for item in created_crews.values() if item[0].resource_id not in known_labels)
        self.db.add(RevisionSnapshot(tenant_id=self.tenant,revision_id=identifier,problem_data=encode_problem(new_problem),source_data=source_data))
        prior_crews=self.query(RevisionCrew).filter_by(revision_id=revision.revision_id).all()
        for crew in prior_crews:
            self.db.add(RevisionCrew(tenant_id=self.tenant,revision_id=identifier,resource_id=crew.resource_id,driver_id=crew.driver_id,
                vehicle_id=crew.vehicle_id,driver_version=crew.driver_version,vehicle_version=crew.vehicle_version,
                confirmed_by=crew.confirmed_by,confirmed_at=crew.confirmed_at))
        for resource,label,driver_id,vehicle_id,driver_version,vehicle_version in created_crews.values():
            if resource.resource_id not in {crew.resource_id for crew in prior_crews}:
                self.db.add(RevisionCrew(tenant_id=self.tenant,revision_id=identifier,resource_id=resource.resource_id,driver_id=driver_id,
                    vehicle_id=vehicle_id,driver_version=driver_version,vehicle_version=vehicle_version,confirmed_by=self.user.id,confirmed_at=datetime.now(timezone.utc)))
        for row in rows:
            reason=cancelled.get(row.trip_id,row.cancellation_reason)
            is_cancelled=row.is_cancelled or row.trip_id in cancelled
            self.db.add(RevisionAssignment(tenant_id=self.tenant,revision_id=identifier,trip_id=row.trip_id,resource_id=chosen.get(row.trip_id,row.resource_id),
                start_minutes=row.start_minutes,end_minutes=row.end_minutes,start_station=row.start_station,end_station=row.end_station,is_locked=row.is_locked and row.trip_id not in unlocked,
                is_cancelled=is_cancelled,cancellation_reason=reason))
        self.db.add(SchedulingAuditLog(tenant_id=self.tenant,revision_id=identifier,action='create_published_successor',actor=str(self.user.id),
            details={'base_publication_id':publication.publication_id,'reason':request.reason,'reviewed_not_started':request.reviewed_not_started,'unlocked_trips':sorted(unlocked)}))
        self.db.flush()
        response=jsonable_encoder(serialize(self.db,successor))
        self.db.add(ScheduleChange(tenant_id=self.tenant,publication_id=publication.publication_id,base_revision_id=revision.revision_id,
            successor_revision_id=identifier,request_id=str(request.request_id),payload_hash=digest,actor_id=self.user.id,
            reason=request.reason,changes=preview['changes'],response_data=response,created_at=datetime.now(timezone.utc)))
        self.db.flush();return response
