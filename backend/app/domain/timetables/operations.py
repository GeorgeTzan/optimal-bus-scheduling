"""Canonical operational inputs. Callers own commits so multi-record operations remain atomic."""
import hashlib,json
from dataclasses import replace
from datetime import date,datetime,timedelta,timezone
from fastapi import HTTPException
from app.domain.resources.reference_reservations import check_reference
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from db.models import KTEL
from app.domain.identity.tenant_session import tenant_transaction
from app.domain.workforce.models import WorkforceDriver
from app.domain.fleet.models import Vehicle
from app.domain.timetables.models import Station,Route,ServiceTemplate,TripInstance,ServiceException,DailyPairing,StationTransfer,ServiceConnection
from app.domain.timetables.calendar import CalendarRule,CalendarException,resolve_service_day
from app.domain.timetables.time_service import AmbiguousLocalTimeError,NonExistentLocalTimeError
from app.domain.timetables.operational_schemas import TimetableCreate
from app.domain.optimization.adapter import OperationalSnapshot,SyntheticResourcePair
from app.domain.timetables.display_clock import frozen_clock
from app.domain.timetables.connection_graph import linear_chains,ConnectionGraphError,connection_day_issues

CALENDAR_FIELDS=('valid_from','valid_until','operating_weekdays','departure_time','arrival_time','arrival_day_offset')
TEMPLATE_FIELDS=(*CALENDAR_FIELDS,'trip_code','allowed_bus_types','is_active')
EXCEPTION_FIELDS=('action','departure_time','arrival_time','arrival_day_offset','fold_start','fold_end')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def day(value):return date.fromisoformat(value) if isinstance(value,str) else value


def utc(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def invalid(code,message,**fields):raise HTTPException(422,{'code':code,'message':message,**fields})


def validate(model,values):
    try:return model.model_validate(values)
    except ValidationError as error:
        raise HTTPException(422,error.errors(include_context=False,include_url=False)) from None


def station_facts(station):
    return {'id':station.id,'is_active':station.is_active,'is_depot':station.is_depot,
            'latitude':station.latitude,'longitude':station.longitude}


def pairing_fingerprint(driver,vehicle,home):
    return fingerprint({'driver':{'id':driver.id,'active':driver.is_active,'home':driver.home_station_id,
            'daily':driver.max_daily_driving_minutes,'continuous':driver.max_continuous_driving_minutes,'rest':driver.min_daily_rest_minutes},
        'vehicle':{'id':vehicle.id,'active':vehicle.is_active,'home':vehicle.home_station_id,'type':vehicle.bus_type},
        'home':station_facts(home)})


class OperationsService:
    def __init__(self,db,tenant_id,actor_id=None):self.db=db;self.tenant_id=tenant_id;self.actor_id=actor_id

    def lock(self):return self.db.query(KTEL).filter_by(id=self.tenant_id).with_for_update().one()

    def query(self,model):return self.db.query(model).filter(model.tenant_id==self.tenant_id)

    def get(self,model,identifier,active=False):
        query=self.query(model).filter(model.id==identifier).populate_existing()
        if active:query=query.filter(model.is_active.is_(True))
        with self.db.no_autoflush:
            result=query.first()
        if result is None:
            if active:invalid('record_unavailable','Choose an active record from your organization.')
            raise HTTPException(404,'Record not found in your organization.')
        return result

    def flush(self,code='reference_exists'):
        try:self.db.flush()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(409,{'code':code,'message':'A record with this reference, date or resource already exists. Review the existing record.'}) from None

    def station_view(self,station):
        return {key:getattr(station,key) for key in ('id','code','name_el','name_en','version')}

    def template_data(self,template):
        route=self.get(Route,template.route_id)
        return {**{key:getattr(template,key) for key in TEMPLATE_FIELDS},'origin_station_id':route.origin_station_id,
                'destination_station_id':route.destination_station_id,'distance_km':route.distance_km}

    def template_view(self,template):
        data=self.template_data(template)
        try:TimetableCreate.model_validate(data);ready=True
        except ValidationError:ready=False
        return {**data,'id':template.id,'version':template.version,'calendar_ready':ready,
            'origin':self.station_view(self.get(Station,data['origin_station_id'])),
            'destination':self.station_view(self.get(Station,data['destination_station_id']))}

    def route(self,origin,destination,distance):
        self.get(Station,origin,True);self.get(Station,destination,True)
        result=self.query(Route).filter_by(origin_station_id=origin,destination_station_id=destination,distance_km=distance).order_by(Route.id).first()
        if result is None:
            result=Route(tenant_id=self.tenant_id,origin_station_id=origin,destination_station_id=destination,
                         distance_km=distance,typical_duration_minutes=None)
            self.db.add(result);self.db.flush()
        return result

    def create_template(self,request):
        self.lock();values=request.model_dump()
        check_reference(self.db,self.tenant_id,'timetable',values['trip_code'])
        route=self.route(request.origin_station_id,request.destination_station_id,request.distance_km)
        row=ServiceTemplate(tenant_id=self.tenant_id,route_id=route.id,**{key:values[key] for key in TEMPLATE_FIELDS})
        self.db.add(row);self.flush('trip_reference_exists');return self.template_view(row)

    def update_template(self,identifier,request):
        self.lock();row=self.get(ServiceTemplate,identifier)
        if row.version!=request.version:raise HTTPException(409,{'code':'stale_version','message':'This timetable changed. Refresh before saving.'})
        changes=request.model_dump(exclude_unset=True,exclude={'version'})
        check_reference(self.db,self.tenant_id,'timetable',changes.get('trip_code'),row.id)
        if changes=={'is_active':False}:
            row.is_active=False;row.version+=1;self.db.flush();return self.template_view(row)
        values=validate(TimetableCreate,{**self.template_data(row),**changes}).model_dump()
        row.route_id=self.route(values['origin_station_id'],values['destination_station_id'],values['distance_km']).id
        for key in TEMPLATE_FIELDS:setattr(row,key,values[key])
        row.version+=1;self.flush('trip_reference_exists');return self.template_view(row)

    def exception_view(self,row):
        return {**{key:getattr(row,key) for key in EXCEPTION_FIELDS},'id':row.id,'service_date':row.service_date,'version':row.version}

    def save_exception(self,template_id,request,identifier=None):
        self.lock();template=self.get(ServiceTemplate,template_id)
        if identifier is None:
            values=request.model_dump();service_date=values.pop('service_date')
            exception=validate(CalendarException,values)
            row=ServiceException(tenant_id=self.tenant_id,template_id=template.id,service_date=service_date)
            self.db.add(row)
        else:
            row=self.get(ServiceException,identifier)
            if row.template_id!=template.id:raise HTTPException(404,'Date exception not found')
            if row.version!=request.version:raise HTTPException(409,{'code':'stale_version','message':'This date exception changed. Refresh before saving.'})
            exception=validate(CalendarException,{**{key:getattr(row,key) for key in EXCEPTION_FIELDS},
                       **request.model_dump(exclude_unset=True,exclude={'version'})})
            service_date=row.service_date;row.version+=1
        if template.valid_from and template.valid_until and not template.valid_from<=service_date<=template.valid_until:
            invalid('outside_validity','Choose a date within the timetable validity range, or extend that range.')
        for key,value in exception.model_dump().items():setattr(row,key,value)
        self.flush('date_exception_exists');return self.exception_view(row)

    def pairing_entities(self,row):
        return self.get(WorkforceDriver,row.driver_id),self.get(Vehicle,row.vehicle_id),self.get(Station,row.home_station_id)

    def pairing_view(self,row):
        driver,vehicle,home=self.pairing_entities(row)
        current=pairing_fingerprint(driver,vehicle,home)
        return {'id':row.id,'version':row.version,'service_date':row.service_date,'driver_id':driver.id,'vehicle_id':vehicle.id,
            'home_station_id':home.id,'is_active':row.is_active,'is_confirmed':row.is_confirmed,
            'needs_review':bool(row.is_active and (not row.is_confirmed or current!=row.confirmed_source_hash)),
            'driver_name':f'{driver.first_name} {driver.last_name}'.strip(),'driver_code':driver.code,
            'vehicle_label':vehicle.registration_plate or vehicle.code,'bus_type':vehicle.bus_type,
            'home_station':self.station_view(home),'driver_version':driver.version,'vehicle_version':vehicle.version,
            'home_station_version':home.version,'confirmed_at':row.confirmed_at}

    def save_pairing(self,request,identifier=None):
        self.lock()
        if identifier is None:
            row=DailyPairing(tenant_id=self.tenant_id,service_date=request.service_date,
                driver_id=request.driver_id,vehicle_id=request.vehicle_id,home_station_id=request.home_station_id,is_active=True,is_confirmed=False)
            self.db.add(row)
        else:
            row=self.get(DailyPairing,identifier)
            if row.version!=request.version:raise HTTPException(409,{'code':'stale_version','message':'This pairing changed. Refresh before saving.'})
            previous_identity=(row.driver_id,row.vehicle_id,row.home_station_id,row.is_active)
            for key in ('driver_id','vehicle_id','home_station_id','is_active'):
                if key in request.model_fields_set and getattr(request,key) is not None:setattr(row,key,getattr(request,key))
            row.version+=1
        archived=identifier is not None and request.is_active is False
        if row.is_active is False and request.confirm:invalid('archived_pairing','An archived pairing cannot be confirmed.')
        driver=self.get(WorkforceDriver,row.driver_id,not archived);vehicle=self.get(Vehicle,row.vehicle_id,not archived);home=self.get(Station,row.home_station_id,not archived)
        if request.confirm:
            expected=(request.driver_version,request.vehicle_version,request.home_station_version)
            if expected!=(driver.version,vehicle.version,home.version):
                raise HTTPException(409,{'code':'source_changed','message':'Driver, vehicle or base details changed. Review them before confirming.'})
            row.is_confirmed=True;row.confirmed_by=self.actor_id;row.confirmed_at=datetime.now(timezone.utc)
            row.confirmed_source_hash=pairing_fingerprint(driver,vehicle,home)
            row.confirmed_sources={'driver_version':driver.version,'vehicle_version':vehicle.version,'home_station_version':home.version}
        elif identifier is not None and (request.confirm is False or not row.is_active or previous_identity!=(row.driver_id,row.vehicle_id,row.home_station_id,row.is_active)):
            row.is_confirmed=False;row.confirmed_by=None;row.confirmed_at=None;row.confirmed_source_hash=None
        self.flush('pairing_conflict');return self.pairing_view(row)

    def copy_pairings(self,request):
        self.lock()
        if request.from_date==request.to_date:invalid('same_service_day','Choose different service dates.')
        if self.query(DailyPairing).filter_by(service_date=request.to_date,is_active=True).first():
            raise HTTPException(409,{'code':'pairings_exist','message':'Review the existing pairings on the target day before copying another day.'})
        previous=self.query(DailyPairing).filter_by(service_date=request.from_date,is_active=True).order_by(DailyPairing.id).all()
        if not previous:invalid('no_pairings_to_copy','There are no saved pairings on the chosen source day.')
        for row in previous:
            self.get(WorkforceDriver,row.driver_id,True);self.get(Vehicle,row.vehicle_id,True);self.get(Station,row.home_station_id,True)
        copies=[DailyPairing(tenant_id=self.tenant_id,service_date=request.to_date,driver_id=row.driver_id,
            vehicle_id=row.vehicle_id,home_station_id=row.home_station_id,is_active=True,is_confirmed=False) for row in previous]
        self.db.add_all(copies);self.flush('pairing_conflict')
        return {'items':[self.pairing_view(row) for row in copies]}

    def transfer_view(self,row):
        origin=self.get(Station,row.origin_station_id);destination=self.get(Station,row.destination_station_id)
        return {'id':row.id,'version':row.version,'origin':self.station_view(origin),'destination':self.station_view(destination),
            'origin_station_id':origin.id,'destination_station_id':destination.id,'minutes':row.minutes,'source_note':row.source_note,
            'needs_review':row.confirmed_source_hash!=fingerprint([station_facts(origin),station_facts(destination)])}

    def save_transfer(self,request,identifier=None):
        self.lock()
        if identifier is None:
            if request.origin_station_id==request.destination_station_id:invalid('same_station','Choose two different stations.')
            row=StationTransfer(tenant_id=self.tenant_id,origin_station_id=request.origin_station_id,destination_station_id=request.destination_station_id)
            self.db.add(row)
        else:
            row=self.get(StationTransfer,identifier)
            if row.version!=request.version:raise HTTPException(409,{'code':'stale_version','message':'This transfer duration changed. Refresh before saving.'})
            row.version+=1
        origin=self.get(Station,row.origin_station_id,True);destination=self.get(Station,row.destination_station_id,True)
        row.minutes=request.minutes
        if identifier is None or 'source_note' in request.model_fields_set:row.source_note=request.source_note
        row.confirmed_by=self.actor_id
        row.confirmed_at=datetime.now(timezone.utc);row.confirmed_source_hash=fingerprint([station_facts(origin),station_facts(destination)])
        self.flush('transfer_exists');return self.transfer_view(row)


def materialize_service_date(db,tenant_id,service_date,template_versions=None):
    service_date=day(service_date)
    with tenant_transaction(db,tenant_id):
        service=OperationsService(db,tenant_id);tenant=service.lock()
        templates=service.query(ServiceTemplate).filter_by(is_active=True).order_by(ServiceTemplate.id).all()
        current={row.id:row.version for row in templates}
        if template_versions is not None and {int(key):value for key,value in template_versions.items()}!=current:
            raise HTTPException(409,{'code':'source_changed','message':'Timetables changed. Refresh their saved versions before preparing this day.'})
        exceptions={row.template_id:row for row in service.query(ServiceException).filter_by(service_date=service_date).all()}
        prepared=[];issues=[]
        for template in templates:
            try:
                stored=exceptions.get(template.id)
                exception=CalendarException.model_validate({key:getattr(stored,key) for key in EXCEPTION_FIELDS}) if stored else None
                if exception and exception.action=='cancel':continue
                rule=CalendarRule.model_validate({key:getattr(template,key) for key in CALENDAR_FIELDS})
                instant=resolve_service_day(rule,service_date,tenant.timezone,exception)
                if instant is None:continue
                if not template.allowed_bus_types:raise ValueError('Choose eligible vehicle types for this trip')
                route=service.get(Route,template.route_id)
                service.get(Station,route.origin_station_id,True);service.get(Station,route.destination_station_id,True)
                payload={'template_id':template.id,'template_version':template.version,'service_date':service_date.isoformat(),
                    'calendar':rule.model_dump(mode='json'),'exception':exception.model_dump(mode='json') if exception else None,
                    'exception_version':stored.version if stored else None,'timezone':tenant.timezone,
                    'route':{'id':route.id,'version':route.version,'origin_station_id':route.origin_station_id,
                             'destination_station_id':route.destination_station_id,'distance_km':route.distance_km},
                    'allowed_bus_types':list(template.allowed_bus_types),'start_utc':instant.start_utc.isoformat(),'end_utc':instant.end_utc.isoformat()}
                prepared.append((template,route,payload,instant))
            except (AmbiguousLocalTimeError,NonExistentLocalTimeError,ValidationError,ValueError) as error:
                code='ambiguous_local_time' if isinstance(error,AmbiguousLocalTimeError) else 'nonexistent_local_time' if isinstance(error,NonExistentLocalTimeError) else 'calendar_incomplete' if isinstance(error,ValidationError) else 'invalid_trip_time'
                for detail in getattr(error,'issues',None) or [{}]:
                    issues.append({'code':code,'trip_code':template.trip_code,'service_date':service_date.isoformat(),
                        'template_id':template.id,'message':str(error),**detail})
        if issues:raise HTTPException(422,{'code':'day_needs_review','issues':issues,'message':'Review the highlighted dated services before continuing.'})
        results=[]
        for template,route,payload,instant in prepared:
            digest=fingerprint(payload)
            existing=service.query(TripInstance).filter_by(template_id=template.id,service_date=service_date,source_hash=digest).first()
            if existing is None:
                existing=TripInstance(tenant_id=tenant_id,template_id=template.id,template_version=template.version,
                    calendar_exception_version=payload['exception_version'],trip_code=template.trip_code,service_date=service_date,
                    origin_station_id=route.origin_station_id,destination_station_id=route.destination_station_id,
                    start_utc=instant.start_utc,end_utc=instant.end_utc,source_hash=digest,properties={'materialization':payload})
                db.add(existing);db.flush()
            results.append(existing)
        return results


def trip_view(row):
    return {'id':row.id,'trip_code':row.trip_code,'service_date':row.service_date,'template_id':row.template_id,
        'template_version':row.template_version,'source_hash':row.source_hash,
        'start_utc':utc(row.start_utc).isoformat(),'end_utc':utc(row.end_utc).isoformat(),
        'duration_minutes':int((utc(row.end_utc)-utc(row.start_utc)).total_seconds()/60)}


def build_operational_snapshot(db,tenant_id,service_date):
    service_date=day(service_date)
    with tenant_transaction(db,tenant_id):
        service=OperationsService(db,tenant_id);tenant=service.lock()
        trips=materialize_service_date(db,tenant_id,service_date)
        if not trips:invalid('no_services','No services operate on this date. Choose another day or add a dated extra service.')
        pairings=service.query(DailyPairing).filter_by(service_date=service_date,is_active=True).order_by(DailyPairing.id).all()
        if not pairings:invalid('pairings_required','Confirm the drivers and vehicles for this service date first.')
        resources=[];resource_labels=[];needed=set();versions={'templates':{},'drivers':{},'vehicles':{},'stations':{},'pairings':{},'transfers':{},'routes':{},'exceptions':{},'connections':{}}
        for pairing in pairings:
            view=service.pairing_view(pairing)
            driver,vehicle,home=service.pairing_entities(pairing)
            if view['needs_review'] or not all((driver.is_active,vehicle.is_active,home.is_active)):
                invalid('pairing_needs_review',f"Review the pairing for {view['driver_name']} and {view['vehicle_label']}.")
            resources.append(SyntheticResourcePair(driver.id,vehicle.id,home.code,bus_type=vehicle.bus_type,id=f'PAIR_{pairing.id}'))
            resource_labels.append({**view,'resource_id':f'PAIR_{pairing.id}','vehicle_code':vehicle.code,'home_station_code':home.code})
            needed.add(home.id);versions['drivers'][str(driver.id)]=driver.version;versions['vehicles'][str(vehicle.id)]=vehicle.version
            versions['pairings'][str(pairing.id)]=pairing.version
        raw=[];trip_labels=[]
        for trip in trips:
            payload=trip.properties['materialization'];rule=payload['calendar'];override=payload['exception'] or {}
            origin=service.get(Station,trip.origin_station_id,True);destination=service.get(Station,trip.destination_station_id,True)
            needed.update((origin.id,destination.id));versions['templates'][str(trip.template_id)]=trip.template_version
            versions['routes'][str(payload['route']['id'])]=payload['route']['version']
            versions['exceptions'][str(trip.template_id)]=trip.calendar_exception_version or 0
            def effective(key):return override[key] if override.get(key) is not None else rule[key]
            raw.append({'id':f'TRIP_{trip.id}','origin':origin.code,'destination':destination.code,
                'start_time':effective('departure_time'),'end_time':effective('arrival_time'),'arrival_day_offset':effective('arrival_day_offset'),
                'fold_start':override.get('fold_start'),'fold_end':override.get('fold_end'),'allowed_bus_types':payload['allowed_bus_types']})
            trip_labels.append({**trip_view(trip),'id':f'TRIP_{trip.id}','trip_code':trip.trip_code,
                'origin':service.station_view(origin),'destination':service.station_view(destination),'distance_km':payload['route']['distance_km'],
                'departure_local':effective('departure_time'),'arrival_local':effective('arrival_time'),'arrival_day_offset':effective('arrival_day_offset')})
        stations={identifier:service.get(Station,identifier,True) for identifier in sorted(needed)}
        transfers={};transfer_labels=[]
        for transfer in service.query(StationTransfer).filter(StationTransfer.origin_station_id.in_(needed),StationTransfer.destination_station_id.in_(needed)).order_by(StationTransfer.id).all():
            if not service.transfer_view(transfer)['needs_review']:
                transfers[(stations[transfer.origin_station_id].code,stations[transfer.destination_station_id].code)]=transfer.minutes
                transfer_labels.append({'id':transfer.id,'version':transfer.version,'origin_station_code':stations[transfer.origin_station_id].code,
                    'destination_station_code':stations[transfer.destination_station_id].code,'minutes':transfer.minutes})
                versions['transfers'][str(transfer.id)]=transfer.version
        missing=[{'origin':service.station_view(origin),'destination':service.station_view(destination)}
            for origin in stations.values() for destination in stations.values() if origin.id!=destination.id and (origin.code,destination.code) not in transfers]
        if missing:invalid('transfers_required','Enter verified travel durations between the required stations.',links=missing)
        for identifier,station in stations.items():versions['stations'][str(identifier)]=station.version
        from app.domain.office.availability import availability_for_resources
        clock=frozen_clock(service_date,tenant.timezone);origin_utc=datetime.fromisoformat(clock['service_day_start_utc'])
        horizon_end=max(utc(trip.end_utc) for trip in trips)+timedelta(minutes=max(transfers.values(),default=0))
        keys=[(pair.driver_id,pair.vehicle_id) for pair in resources];found=availability_for_resources(db,tenant_id,keys,origin_utc,horizon_end)
        unknown=[{'driver_id':pair.driver_id,'driver_name':label['driver_name']} for pair,label in zip(resources,resource_labels) if found[(pair.driver_id,pair.vehicle_id)].windows is None]
        if unknown:invalid('working_windows_required','Record working time for these drivers before creating a draft.',drivers=unknown)
        minutes=lambda moment:int((moment-origin_utc).total_seconds()//60)
        resources=[replace(pair,available_windows=tuple((minutes(start),minutes(end)) for start,end in found[key].windows)) for pair,key in zip(resources,keys)]
        availability={'fingerprint':fingerprint([found[key].fingerprint for key in keys]),'start_utc':origin_utc.isoformat(),'end_utc':horizon_end.isoformat(),
            'resources':{pair.resource_id:{'windows':[list(window) for window in pair.available_windows],'fingerprint':found[key].fingerprint,
                'warnings':list(found[key].warnings),'findings':list(found[key].findings)} for pair,key in zip(resources,keys)}}
        links=service.query(ServiceConnection).filter_by(is_active=True).order_by(ServiceConnection.id).all()
        try:linear_chains((link.incoming_template_id,link.outgoing_template_id) for link in links)
        except ConnectionGraphError as error:invalid(error.code,str(error))
        trip_by_template={trip.template_id:f'TRIP_{trip.id}' for trip in trips}
        applicable=[link for link in links if link.incoming_template_id in trip_by_template and link.outgoing_template_id in trip_by_template]
        connections=tuple((trip_by_template[link.incoming_template_id],trip_by_template[link.outgoing_template_id]) for link in applicable)
        versions['connections']={str(link.id):link.version for link in applicable}
        source={'source':'operational','source_schema_version':'ktel-operational-v2','service_date':service_date.isoformat(),**clock,'availability':availability,
                'resources':resource_labels,'trips':trip_labels,'stations':[service.station_view(row) for row in stations.values()],
                'source_versions':versions,'transfers':transfer_labels,
                'connections':[{'id':link.id,'version':link.version,'incoming_trip_id':trip_by_template[link.incoming_template_id],
                    'outgoing_trip_id':trip_by_template[link.outgoing_template_id]} for link in applicable]}
        # JSON data contains dates in views; normalize without retaining ORM objects or mutable source rows.
        from fastapi.encoders import jsonable_encoder
        source=jsonable_encoder(source)
        return OperationalSnapshot(tenant_id,service_date,resources,raw,snapshot_hash=fingerprint(without_advice(source)),
            transfer_durations=transfers,source_data=source,timezone=tenant.timezone,connections=connections,availability_enforced=True)


def without_advice(source):
    """Pending-leave warnings are advice, not input: recording or deciding a request must not turn a valid draft into a new one."""
    resources={key:{name:value for name,value in item.items() if name not in ('warnings','findings')} for key,item in source['availability']['resources'].items()}
    return {**source,'availability':{**source['availability'],'resources':resources}}


def dated_trip_views(db,tenant_id,service_date):
    """Read current materializations without creating rows or modifying historical inputs."""
    from zoneinfo import ZoneInfo
    service_date=day(service_date);service=OperationsService(db,tenant_id)
    tenant=db.query(KTEL).filter_by(id=tenant_id).one()
    templates={row.id:row for row in service.query(ServiceTemplate).filter_by(is_active=True).all()}
    exceptions={row.template_id:row for row in service.query(ServiceException).filter_by(service_date=service_date).all()}
    result=[]
    for row in service.query(TripInstance).filter_by(service_date=service_date).order_by(TripInstance.id).all():
        template=templates.get(row.template_id);exception=exceptions.get(row.template_id)
        if template is None or row.template_version!=template.version:continue
        if row.calendar_exception_version!=(exception.version if exception else None):continue
        if exception and exception.action=='cancel':continue
        payload=(row.properties or {}).get('materialization',{})
        if not row.source_hash or payload.get('timezone')!=tenant.timezone:continue
        route=service.get(Route,template.route_id)
        if payload.get('route',{}).get('version')!=route.version:continue
        origin=service.get(Station,row.origin_station_id);destination=service.get(Station,row.destination_station_id)
        local_start=utc(row.start_utc).astimezone(ZoneInfo(tenant.timezone))
        local_end=utc(row.end_utc).astimezone(ZoneInfo(tenant.timezone))
        result.append({**trip_view(row),'origin':service.station_view(origin),'destination':service.station_view(destination),
            'departure_local':local_start.strftime('%H:%M'),'arrival_local':local_end.strftime('%H:%M'),
            'arrival_day_offset':(local_end.date()-service_date).days,'distance_km':payload['route']['distance_km'],
            'fold_start':(payload.get('exception') or {}).get('fold_start'),'fold_end':(payload.get('exception') or {}).get('fold_end')})
    return result


def operational_readiness(db,tenant_id,service_date=None):
    from zoneinfo import ZoneInfo
    from app.domain.resources.service import readiness
    service=OperationsService(db,tenant_id);tenant=db.query(KTEL).filter_by(id=tenant_id).one()
    selected=day(service_date) if service_date else datetime.now(ZoneInfo(tenant.timezone)).date()
    base=readiness(db,tenant_id);issues=[];needed=set();operating=[];trip_facts={}
    templates=service.query(ServiceTemplate).filter_by(is_active=True).order_by(ServiceTemplate.id).all()
    exceptions={row.template_id:row for row in service.query(ServiceException).filter_by(service_date=selected).all()}
    for template in templates:
        try:
            stored=exceptions.get(template.id)
            exception=CalendarException.model_validate({key:getattr(stored,key) for key in EXCEPTION_FIELDS}) if stored else None
            if exception and exception.action=='cancel':continue
            rule=CalendarRule.model_validate({key:getattr(template,key) for key in CALENDAR_FIELDS})
            instant=resolve_service_day(rule,selected,tenant.timezone,exception)
            if instant is None:continue
            if not template.allowed_bus_types:raise ValueError('Choose eligible vehicle types for this trip')
            route=service.get(Route,template.route_id)
            for identifier in (route.origin_station_id,route.destination_station_id):
                station=service.get(Station,identifier)
                if not station.is_active:raise ValueError('Review an archived station used by this service')
                needed.add(identifier)
            operating.append(template)
            trip_facts[template.id]={'trip_code':template.trip_code,'start':instant.start_offset_minutes,'end':instant.end_offset_minutes,
                'origin':route.origin_station_id,'destination':route.destination_station_id,'types':template.allowed_bus_types}
        except (AmbiguousLocalTimeError,NonExistentLocalTimeError,ValidationError,ValueError) as error:
            code='calendar_incomplete' if isinstance(error,ValidationError) else 'invalid_trip_time'
            for detail in getattr(error,'issues',None) or [{}]:
                issues.append({'code':code,'template_id':template.id,'trip_code':template.trip_code,
                    'service_date':selected.isoformat(),'message':str(error),**detail})
    pairings=service.query(DailyPairing).filter_by(service_date=selected,is_active=True).order_by(DailyPairing.id).all()
    confirmed=[];driver_names={}
    for pairing in pairings:
        view=service.pairing_view(pairing)
        if view['needs_review']:continue
        driver,vehicle,home=service.pairing_entities(pairing)
        if all((driver.is_active,vehicle.is_active,home.is_active)):
            confirmed.append((pairing,vehicle));needed.add(home.id);driver_names[pairing.id]=(driver.id,view['driver_name'])
    if not operating and not issues:issues.append({'code':'no_services','message':'No services operate on this date.'})
    if not pairings:issues.append({'code':'pairings_required','message':'Choose the drivers and vehicles for this date.'})
    elif len(confirmed)!=len(pairings):issues.append({'code':'pairing_needs_review','message':'Review and confirm the highlighted pairings.'})
    types={vehicle.bus_type for _,vehicle in confirmed}
    for template in operating:
        if not types.intersection(template.allowed_bus_types):
            issues.append({'code':'no_eligible_vehicle','trip_code':template.trip_code,'message':'Confirm a suitable vehicle category for this service.'})
    stations={identifier:service.get(Station,identifier) for identifier in sorted(needed)}
    known=set();transfer_minutes={}
    for row in service.query(StationTransfer).filter(StationTransfer.origin_station_id.in_(needed),StationTransfer.destination_station_id.in_(needed)).all():
        if not service.transfer_view(row)['needs_review']:
            known.add((row.origin_station_id,row.destination_station_id));transfer_minutes[(row.origin_station_id,row.destination_station_id)]=row.minutes
    missing_count=len(stations)*(len(stations)-1)-len(known)
    missing=[]
    for origin in stations.values():
        for destination in stations.values():
            if origin.id!=destination.id and (origin.id,destination.id) not in known:
                missing.append({'origin':service.station_view(origin),'destination':service.station_view(destination)})
                if len(missing)>=100:break
        if len(missing)>=100:break
    if operating and confirmed and len(confirmed)==len(pairings):
        from app.domain.office.availability import availability_for_resources
        origin_utc=datetime.fromisoformat(frozen_clock(selected,tenant.timezone)['service_day_start_utc'])
        horizon_end=origin_utc+timedelta(minutes=max(fact['end'] for fact in trip_facts.values())+max(transfer_minutes.values(),default=0))
        keys=[(pairing.driver_id,pairing.vehicle_id) for pairing,_ in confirmed]
        found=availability_for_resources(db,tenant_id,keys,origin_utc,horizon_end)
        unknown=[{'driver_id':driver_names[pairing.id][0],'driver_name':driver_names[pairing.id][1]} for pairing,_ in confirmed if found[(pairing.driver_id,pairing.vehicle_id)].windows is None]
        if unknown:issues.append({'code':'working_windows_required','message':'Record working time for these drivers in the Office section.','drivers':unknown})
    links=service.query(ServiceConnection).filter_by(is_active=True).all()
    try:
        linear_chains((link.incoming_template_id,link.outgoing_template_id) for link in links)
        applicable=[(link.incoming_template_id,link.outgoing_template_id) for link in links if link.incoming_template_id in trip_facts and link.outgoing_template_id in trip_facts]
        issues.extend(connection_day_issues(applicable,trip_facts,types if len(confirmed)==len(pairings) else set(),transfer_minutes))
    except ConnectionGraphError as error:issues.append({'code':error.code,'message':str(error)})
    saved=dated_trip_views(db,tenant_id,selected)
    inputs_ready=bool(operating and not issues and missing_count==0)
    return {**base,'service_date':selected,'timezone':tenant.timezone,'template_versions':{str(row.id):row.version for row in templates},
        'operating_trips':len(operating),'pairings':len(pairings),'confirmed_pairings':len(confirmed),
        'issues':issues,'missing_transfers':missing,'missing_transfer_count':missing_count,'required_station_ids':sorted(needed),'inputs_ready':inputs_ready,
        'day_prepared':bool(operating and not issues and len(saved)==len(operating)),
        'prepared_trips':len(saved)}
