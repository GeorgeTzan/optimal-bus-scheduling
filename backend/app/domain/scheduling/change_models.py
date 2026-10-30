"""Audited, idempotent lineage for a published schedule's draft successor."""
from datetime import datetime,timezone
from sqlalchemy import Column,Integer,String,DateTime,JSON,ForeignKey,ForeignKeyConstraint,UniqueConstraint
from db.database import Base

class ScheduleChange(Base):
    __tablename__='domain_schedule_changes'
    __table_args__=(UniqueConstraint('tenant_id','id'),UniqueConstraint('tenant_id','request_id'),UniqueConstraint('tenant_id','successor_revision_id'),
        ForeignKeyConstraint(['tenant_id','publication_id','base_revision_id'],['domain_publications.tenant_id','domain_publications.publication_id','domain_publications.revision_id']),
        ForeignKeyConstraint(['tenant_id','successor_revision_id'],['domain_schedule_revisions.tenant_id','domain_schedule_revisions.revision_id']),
        ForeignKeyConstraint(['tenant_id','actor_id'],['users.ktel_id','users.id']))
    id=Column(Integer,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    publication_id=Column(String,nullable=False)
    base_revision_id=Column(String,nullable=False)
    successor_revision_id=Column(String,nullable=False)
    request_id=Column(String(36),nullable=False)
    payload_hash=Column(String(64),nullable=False)
    actor_id=Column(Integer,nullable=False)
    reason=Column(String(1000),nullable=False)
    changes=Column(JSON,nullable=False)
    response_data=Column(JSON,nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))


class RevisionCrew(Base):
    __tablename__='domain_revision_crews'
    __table_args__=(UniqueConstraint('tenant_id','id'),UniqueConstraint('tenant_id','revision_id','resource_id'),
        ForeignKeyConstraint(['tenant_id','revision_id'],['domain_schedule_revisions.tenant_id','domain_schedule_revisions.revision_id']),
        ForeignKeyConstraint(['tenant_id','driver_id'],['domain_drivers.tenant_id','domain_drivers.id']),
        ForeignKeyConstraint(['tenant_id','vehicle_id'],['domain_vehicles.tenant_id','domain_vehicles.id']),
        ForeignKeyConstraint(['tenant_id','confirmed_by'],['users.ktel_id','users.id']))
    id=Column(Integer,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    revision_id=Column(String,nullable=False)
    resource_id=Column(String,nullable=False)
    driver_id=Column(Integer,nullable=False)
    vehicle_id=Column(Integer,nullable=False)
    driver_version=Column(Integer,nullable=False)
    vehicle_version=Column(Integer,nullable=False)
    confirmed_by=Column(Integer,nullable=False)
    confirmed_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
