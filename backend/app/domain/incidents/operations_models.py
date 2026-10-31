"""Publication-bound reporting projection and append-only attributed history."""
from datetime import datetime, timezone
from sqlalchemy import Column,Integer,String,DateTime,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint
from db.database import Base


class OperationalTripState(Base):
    __tablename__='domain_operational_trip_states'
    __table_args__=(
        UniqueConstraint('tenant_id','id'),
        UniqueConstraint('tenant_id','publication_id','trip_id'),
        ForeignKeyConstraint(['tenant_id','publication_id','revision_id'],['domain_publications.tenant_id','domain_publications.publication_id','domain_publications.revision_id']),
        ForeignKeyConstraint(['tenant_id','revision_id','trip_id'],['domain_revision_assignments.tenant_id','domain_revision_assignments.revision_id','domain_revision_assignments.trip_id']),
        CheckConstraint('version>0'),
    )
    id=Column(Integer,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    publication_id=Column(String,nullable=False)
    revision_id=Column(String,nullable=False)
    trip_id=Column(String,nullable=False)
    version=Column(Integer,nullable=False)


class OperationalEvent(Base):
    __tablename__='domain_operational_events'
    __table_args__=(
        UniqueConstraint('tenant_id','id'),UniqueConstraint('tenant_id','state_id','id'),
        UniqueConstraint('tenant_id','request_id'),
        ForeignKeyConstraint(['tenant_id','state_id'],['domain_operational_trip_states.tenant_id','domain_operational_trip_states.id']),
        ForeignKeyConstraint(['tenant_id','state_id','resolved_event_id'],['domain_operational_events.tenant_id','domain_operational_events.state_id','domain_operational_events.id']),
        ForeignKeyConstraint(['tenant_id','actor_id'],['users.ktel_id','users.id']),
        CheckConstraint("kind IN ('delay','breakdown','note','departure','completion','resolution')"),
        CheckConstraint("(kind='delay' AND delay_minutes IS NOT NULL AND delay_minutes BETWEEN 0 AND 1440) OR (kind<>'delay' AND delay_minutes IS NULL)"),
        CheckConstraint("(kind='resolution')=(resolved_event_id IS NOT NULL)"),
    )
    id=Column(Integer,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    state_id=Column(Integer,nullable=False,index=True)
    kind=Column(String,nullable=False)
    description=Column(String(2000),nullable=False)
    delay_minutes=Column(Integer,nullable=True)
    actor_id=Column(Integer,nullable=False)
    actor_name=Column(String,nullable=False)
    recorded_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    resolved_event_id=Column(Integer,nullable=True)
    request_id=Column(String(36),nullable=False)
    payload_hash=Column(String(64),nullable=False)
    state_version=Column(Integer,nullable=False)
