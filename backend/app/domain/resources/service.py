"""Tenant-owned canonical registers. All writes use optimistic versions and row locks."""
from fastapi import HTTPException
from app.domain.resources.reference_reservations import check_reference,is_reserved
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from db.models import KTEL
from app.domain.workforce.models import WorkforceDriver
from app.domain.fleet.models import Vehicle
from app.domain.timetables.models import Station,ServiceTemplate,Route,DailyPairing
from app.domain.identity.models import Membership

MODELS={'drivers':WorkforceDriver,'vehicles':Vehicle,'stations':Station}
FIELDS={
 'drivers':('id','code','first_name','last_name','phone','license_number','home_station_id','is_active','version'),
 'vehicles':('id','code','registration_plate','bus_type','capacity','home_station_id','is_active','version'),
 'stations':('id','code','name_el','name_en','is_depot','is_active','latitude','longitude','version'),
}

class ResourceService:
    def __init__(self,db,tenant_id,kind):
        self.db=db;self.tenant_id=tenant_id;self.kind=kind;self.model=MODELS[kind]

    def query(self):
        return self.db.query(self.model).filter(self.model.tenant_id==self.tenant_id)

    def get(self,identifier,lock=False):
        query=self.query().filter(self.model.id==identifier)
        if lock:query=query.populate_existing().with_for_update()
        record=query.first()
        if record is None:raise HTTPException(404,'This record was not found in your organization.')
        return record

    def view(self,record):
        result={field:getattr(record,field) for field in FIELDS[self.kind]}
        if self.kind!='stations':
            home=self.db.query(Station).filter_by(tenant_id=self.tenant_id,id=record.home_station_id).first() if record.home_station_id else None
            result['home_station']={key:getattr(home,key) for key in ('id','code','name_el','name_en')} if home else None
        return result

    def list(self,q,page,page_size,active_only):
        query=self.query()
        if active_only:query=query.filter(self.model.is_active.is_(True))
        if q:
            fields={'drivers':('code','first_name','last_name'),'vehicles':('code','registration_plate'),'stations':('code','name_el','name_en')}[self.kind]
            query=query.filter(or_(*(getattr(self.model,key).icontains(q,autoescape=True) for key in fields)))
        total=query.count()
        return {'items':[self.view(row) for row in query.order_by(self.model.id).offset((page-1)*page_size).limit(page_size)],
                'total':total,'page':page,'page_size':page_size}

    def _reference(self,data):
        identifier=data.get('home_station_id')
        if identifier is not None:
            home=self.db.query(Station).filter_by(tenant_id=self.tenant_id,id=identifier,is_active=True).with_for_update().first()
            if home is None:raise HTTPException(422,{'field':'home_station_id','message':'Choose an active station from your organization.'})

    def _code(self):
        prefix={'drivers':'D','vehicles':'V','stations':'S'}[self.kind]
        number=self.query().count()+1
        while self.query().filter_by(code=f'{prefix}{number:05d}').first() or is_reserved(self.db,self.tenant_id,self.kind,f'{prefix}{number:05d}'):number+=1
        return f'{prefix}{number:05d}'

    def _save(self,record):
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(409,{'code':'reference_exists','message':'This reference or registration already exists. Open the existing record or choose a different reference.'}) from None
        return self.view(record)

    def create(self,request):
        # A shared organization lock serializes generated readable codes and archive/reference checks.
        self.db.query(KTEL).filter_by(id=self.tenant_id).with_for_update().one()
        data=request.model_dump();self._reference(data)
        if not data.get('code'):data['code']=self._code()
        check_reference(self.db,self.tenant_id,self.kind,data['code'])
        if self.kind=='vehicles':check_reference(self.db,self.tenant_id,self.kind,data.get('registration_plate'),registration=True)
        if self.kind=='vehicles' and data.get('registration_plate'):data['registration_plate']=data['registration_plate'].upper()
        if self.kind=='stations' and not data.get('name_en'):data['name_en']=data['name_el']
        record=self.model(tenant_id=self.tenant_id,**data);self.db.add(record)
        return self._save(record)

    def update(self,identifier,request):
        self.db.query(KTEL).filter_by(id=self.tenant_id).with_for_update().one()
        record=self.get(identifier,lock=True)
        if record.version!=request.version:raise HTTPException(409,{'code':'stale_version','message':'Someone updated this record. Refresh before saving your changes.'})
        changes=request.model_dump(exclude_unset=True,exclude={'version'});self._reference(changes)
        check_reference(self.db,self.tenant_id,self.kind,changes.get('code'),record.id)
        if self.kind=='vehicles':check_reference(self.db,self.tenant_id,self.kind,changes.get('registration_plate'),record.id,registration=True)
        if changes.get('is_active') is False:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            tenant=self.db.query(KTEL).filter_by(id=self.tenant_id).one()
            today=datetime.now(ZoneInfo(tenant.timezone)).date()
            link={'drivers':DailyPairing.driver_id,'vehicles':DailyPairing.vehicle_id,'stations':DailyPairing.home_station_id}[self.kind]
            upcoming=self.db.query(DailyPairing.id).filter(DailyPairing.tenant_id==self.tenant_id,DailyPairing.is_active.is_(True),DailyPairing.service_date>=today,link==record.id).first()
            if upcoming:raise HTTPException(409,{'code':'upcoming_pairings','message':'Remove this record from current and upcoming daily pairings before archiving it.'})
            if self.kind=='vehicles':
                from app.domain.fleet.models import VehicleAvailability
                now=datetime.now(ZoneInfo('UTC'))
                if self.db.query(VehicleAvailability.id).filter(VehicleAvailability.tenant_id==self.tenant_id,VehicleAvailability.vehicle_id==record.id,VehicleAvailability.status=='active',
                    or_(VehicleAvailability.end_utc.is_(None),VehicleAvailability.end_utc>now)).first():
                    raise HTTPException(409,{'code':'active_office_periods','message':'Release or cancel this vehicle’s active maintenance or out-of-service period before archiving it.'})
            if self.kind=='stations':
                linked=any(self.db.query(model).filter_by(tenant_id=self.tenant_id,home_station_id=record.id,is_active=True).first() for model in (WorkforceDriver,Vehicle))
                if linked:raise HTTPException(409,{'code':'station_in_use','message':'Move active drivers and vehicles to another station before archiving this station.'})
                in_timetable=self.db.query(ServiceTemplate).join(Route,Route.id==ServiceTemplate.route_id).filter(
                    ServiceTemplate.tenant_id==self.tenant_id,ServiceTemplate.is_active.is_(True),
                    or_(Route.origin_station_id==record.id,Route.destination_station_id==record.id)).first()
                if in_timetable:raise HTTPException(409,{'code':'station_timetable_in_use','message':'Update active timetables to use another station before archiving this station.'})
            if self.kind=='drivers' and self.db.query(Membership).filter_by(tenant_id=self.tenant_id,driver_id=record.id,is_active=True).first():
                raise HTTPException(409,{'code':'driver_account_linked','message':'Remove this driver’s active account link before archiving the driver.'})
        if self.kind=='vehicles' and changes.get('registration_plate'):changes['registration_plate']=changes['registration_plate'].upper()
        for key,value in changes.items():setattr(record,key,value)
        record.version+=1
        return self._save(record)


def readiness(db,tenant_id):
    counts={key:db.query(model).filter_by(tenant_id=tenant_id,is_active=True).count() for key,model in MODELS.items()}
    counts['timetables']=db.query(ServiceTemplate).filter_by(tenant_id=tenant_id,is_active=True).count()
    # Calendar, pairing and transfer readiness are implemented in the next operational slice.
    steps=[{'key':key,'complete':counts[key]>0} for key in ('drivers','vehicles','timetables')]
    return {**counts,'steps':steps,'can_generate_draft':False,'next_step':next((step['key'] for step in steps if not step['complete']),'pairings')}
