"""Versioned optional same-vehicle links, with no internal transaction commits."""
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, StrictBool
from fastapi import HTTPException
from app.domain.timetables.operational_schemas import Positive
from app.domain.timetables.models import ServiceConnection, ServiceTemplate
from app.domain.timetables.operations import OperationsService
from app.domain.timetables.connection_graph import linear_chains, ConnectionGraphError


class ConnectionCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    incoming_template_id:Positive
    outgoing_template_id:Positive
    incoming_template_version:Positive
    outgoing_template_version:Positive
    is_active:StrictBool=True


class ConnectionPatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:Positive
    is_active:StrictBool


class ConnectionService:
    def __init__(self, db, tenant_id, actor_id=None):
        self.db=db;self.tenant_id=tenant_id;self.actor_id=actor_id
        self.ops=OperationsService(db,tenant_id,actor_id)

    def query(self):return self.ops.query(ServiceConnection)

    def validate_graph(self, incoming, outgoing, active=True, exclude=None):
        rows=self.query().filter_by(is_active=True)
        if exclude is not None:rows=rows.filter(ServiceConnection.id!=exclude)
        edges=[(row.incoming_template_id,row.outgoing_template_id) for row in rows.all()]
        if active:edges.append((incoming,outgoing))
        try:linear_chains(edges)
        except ConnectionGraphError as error:raise HTTPException(422,{'code':error.code,'message':str(error)}) from None

    def create(self, request):
        self.ops.lock()
        incoming=self.ops.get(ServiceTemplate,request.incoming_template_id,request.is_active)
        outgoing=self.ops.get(ServiceTemplate,request.outgoing_template_id,request.is_active)
        if incoming.version!=request.incoming_template_version or outgoing.version!=request.outgoing_template_version:
            raise HTTPException(409,{'code':'source_changed','message':'A selected service changed. Choose it again before linking.'})
        if incoming.id == outgoing.id:raise HTTPException(422,{'code':'connection_cycle','message':'Choose two different services.'})
        self.validate_graph(incoming.id,outgoing.id,request.is_active)
        row=ServiceConnection(tenant_id=self.tenant_id,incoming_template_id=incoming.id,outgoing_template_id=outgoing.id,
            is_active=request.is_active,created_by=self.actor_id,updated_by=self.actor_id)
        self.db.add(row);self.ops.flush('connection_exists')
        return self.view(row,{incoming.id:incoming,outgoing.id:outgoing})

    def update(self, identifier, request):
        self.ops.lock();row=self.query().filter_by(id=identifier).populate_existing().with_for_update().first()
        if row is None:raise HTTPException(404,'Connection not found in your workspace.')
        if row.version!=request.version:raise HTTPException(409,{'code':'stale_version','message':'This connection changed. Refresh it before saving.'})
        incoming=self.ops.get(ServiceTemplate,row.incoming_template_id,request.is_active)
        outgoing=self.ops.get(ServiceTemplate,row.outgoing_template_id,request.is_active)
        self.validate_graph(incoming.id,outgoing.id,request.is_active,row.id)
        row.is_active=request.is_active;row.version+=1;row.updated_by=self.actor_id;row.updated_at=datetime.now(timezone.utc)
        self.ops.flush('connection_exists');return self.view(row,{incoming.id:incoming,outgoing.id:outgoing})

    def view(self, row, templates=None):
        def parent(identifier):
            value=templates[identifier] if templates is not None else self.ops.get(ServiceTemplate,identifier)
            return {key:getattr(value,key) for key in ('id','version','trip_code','departure_time','arrival_time','is_active')}
        return {'id':row.id,'version':row.version,'is_active':row.is_active,
                'incoming':parent(row.incoming_template_id),'outgoing':parent(row.outgoing_template_id)}

    def list(self,page,page_size,active_only=False):
        query=self.query()
        if active_only:query=query.filter_by(is_active=True)
        total=query.count();rows=query.order_by(ServiceConnection.id).offset((page-1)*page_size).limit(page_size).all()
        ids={identifier for row in rows for identifier in (row.incoming_template_id,row.outgoing_template_id)}
        templates={row.id:row for row in self.ops.query(ServiceTemplate).filter(ServiceTemplate.id.in_(ids)).all()} if ids else {}
        return {'items':[self.view(row,templates) for row in rows],'total':total,'page':page,'page_size':page_size}
