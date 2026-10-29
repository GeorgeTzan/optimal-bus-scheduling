"""Reusable, paginated empty-vehicle travel times; callers own the transaction."""
from itertools import combinations,islice
from typing import Annotated
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator
from app.domain.timetables.models import Station,StationTransfer
from app.domain.timetables.operations import OperationsService,operational_readiness,station_facts,fingerprint
from app.domain.timetables.operational_schemas import Positive,TransferCreate,TransferPatch


class DirectionEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    origin_station_id:Positive
    destination_station_id:Positive
    origin_version:Positive
    destination_version:Positive
    expected_version:Positive|None
    minutes:Annotated[int,Field(strict=True,ge=0,le=1440)]


class TransferEdits(BaseModel):
    model_config=ConfigDict(extra='forbid')
    items:list[DirectionEdit]=Field(min_length=1,max_length=100)

    @model_validator(mode='after')
    def distinct(self):
        keys=[(row.origin_station_id,row.destination_station_id) for row in self.items]
        if len(set(keys))!=len(keys):raise ValueError('Review each direction only once before saving.')
        if any(first==second for first,second in keys):raise ValueError('Choose two different stations.')
        return self


class TransferEditor:
    def __init__(self,db,tenant_id,actor_id=None):
        self.db=db;self.tenant_id=tenant_id;self.ops=OperationsService(db,tenant_id,actor_id)

    def list(self,service_date,filter_kind,page,page_size):
        ready=operational_readiness(self.db,self.tenant_id,service_date)
        required=set(ready['required_station_ids'])
        stations={row.id:row for row in self.ops.query(Station).all()}
        records={(row.origin_station_id,row.destination_station_id):row for row in self.ops.query(StationTransfer).filter(StationTransfer.origin_station_id!=StationTransfer.destination_station_id).all()}
        valid=set()
        for key,row in records.items():
            if row.confirmed_source_hash==fingerprint([station_facts(stations[key[0]]),station_facts(stations[key[1]])]):valid.add(key)
        applicable={key for key in records if key[0] in required and key[1] in required}
        complete={tuple(sorted(key)) for key in valid if key[0] in required and key[1] in required and (key[1],key[0]) in valid}
        total_directions=len(required)*(len(required)-1)
        counts={'required_directions':total_directions,'saved_directions':len(applicable & valid),
            'missing_directions':total_directions-len(applicable),'review_directions':len(applicable-valid)}
        if filter_kind=='all':
            pairs=sorted({tuple(sorted(key)) for key in records});total=len(pairs)
        else:
            pairs=combinations(sorted(required),2);total=total_directions//2
            if filter_kind=='missing':
                pairs=(key for key in pairs if key not in complete);total-=len(complete)

        def direction(origin,destination):
            row=records.get((origin,destination))
            return {'id':row.id if row else None,'version':row.version if row else None,
                'origin_station_id':origin,'destination_station_id':destination,
                'origin_version':stations[origin].version,'destination_version':stations[destination].version,
                'minutes':row.minutes if row else None,'needs_review':bool(row and (origin,destination) not in valid),
                'can_edit':bool(stations[origin].is_active and stations[destination].is_active)}

        items=[]
        for origin,destination in islice(pairs,(page-1)*page_size,page*page_size):
            items.append({'key':f'{origin}:{destination}','origin':self.ops.station_view(stations[origin]),
                'destination':self.ops.station_view(stations[destination]),'forward':direction(origin,destination),
                'reverse':direction(destination,origin)})
        return {'service_date':ready['service_date'],'timezone':ready['timezone'],'items':items,
            'counts':counts,'total':total,'page':page,'page_size':page_size}

    def save(self,request):
        self.ops.lock()
        checked=[]
        for item in request.items:
            origin=self.ops.get(Station,item.origin_station_id,True)
            destination=self.ops.get(Station,item.destination_station_id,True)
            if origin.version!=item.origin_version or destination.version!=item.destination_version:
                raise HTTPException(409,{'code':'source_changed','message':'Station details changed. Refresh the travel times before saving.'})
            row=self.ops.query(StationTransfer).filter_by(origin_station_id=origin.id,destination_station_id=destination.id).populate_existing().with_for_update().first()
            if (row.version if row else None)!=item.expected_version:
                raise HTTPException(409,{'code':'stale_version','message':'This travel time changed. Refresh it before saving your changes.'})
            checked.append((item,row))
        result=[]
        for item,row in checked:
            if row:
                result.append(self.ops.save_transfer(TransferPatch(version=row.version,minutes=item.minutes),row.id))
            else:
                result.append(self.ops.save_transfer(TransferCreate(origin_station_id=item.origin_station_id,destination_station_id=item.destination_station_id,minutes=item.minutes)))
        return {'items':result}
