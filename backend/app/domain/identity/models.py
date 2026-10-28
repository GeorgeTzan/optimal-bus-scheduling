"""Persisted tenant membership and revocable identities; secrets are stored only as hashes."""
from datetime import datetime,timezone
from sqlalchemy import Column,Integer,String,Boolean,DateTime,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint
from db.database import Base

ROLES=('admin','dispatcher','fleet_manager','driver','management','viewer')


def now():
    return datetime.now(timezone.utc)


class Membership(Base):
    __tablename__='domain_memberships'
    id=Column(Integer,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    user_id=Column(Integer,nullable=False,index=True)
    role=Column(String,nullable=False)
    is_active=Column(Boolean,nullable=False,default=True)
    driver_id=Column(Integer,nullable=True)
    version=Column(Integer,nullable=False,default=1)
    created_at=Column(DateTime(timezone=True),nullable=False,default=now)
    __table_args__=(UniqueConstraint('tenant_id','id'),UniqueConstraint('tenant_id','user_id'),
        ForeignKeyConstraint(['tenant_id','user_id'],['users.ktel_id','users.id']),
        ForeignKeyConstraint(['tenant_id','driver_id'],['domain_drivers.tenant_id','domain_drivers.id']),
        CheckConstraint("role IN ('admin','dispatcher','fleet_manager','driver','management','viewer')"))


class AuthSession(Base):
    __tablename__='domain_auth_sessions'
    id=Column(String,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    user_id=Column(Integer,nullable=False,index=True)
    membership_id=Column(Integer,nullable=False,index=True)
    token_hash=Column(String,nullable=False,unique=True,index=True)
    csrf_hash=Column(String,nullable=False)
    expires_at=Column(DateTime(timezone=True),nullable=False,index=True)
    revoked_at=Column(DateTime(timezone=True),nullable=True)
    created_at=Column(DateTime(timezone=True),nullable=False,default=now)
    __table_args__=(UniqueConstraint('tenant_id','id'),
        ForeignKeyConstraint(['tenant_id','user_id'],['users.ktel_id','users.id']),
        ForeignKeyConstraint(['tenant_id','membership_id'],['domain_memberships.tenant_id','domain_memberships.id']))


class IdentityToken(Base):
    __tablename__='domain_identity_tokens'
    id=Column(String,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    token_hash=Column(String,nullable=False,unique=True,index=True)
    kind=Column(String,nullable=False,index=True)
    email=Column(String,nullable=False)
    role=Column(String,nullable=True)
    user_id=Column(Integer,nullable=True)
    expires_at=Column(DateTime(timezone=True),nullable=False,index=True)
    consumed_at=Column(DateTime(timezone=True),nullable=True)
    driver_id=Column(Integer,nullable=True)
    revoked_at=Column(DateTime(timezone=True),nullable=True)
    created_at=Column(DateTime(timezone=True),nullable=False,default=now)
    __table_args__=(UniqueConstraint('tenant_id','id'),
        ForeignKeyConstraint(['tenant_id','user_id'],['users.ktel_id','users.id']),
        ForeignKeyConstraint(['tenant_id','driver_id'],['domain_drivers.tenant_id','domain_drivers.id']),
        CheckConstraint("kind IN ('invitation','reset')"),
        CheckConstraint("role IS NULL OR role IN ('admin','dispatcher','fleet_manager','driver','management','viewer')"))


class EmailOutbox(Base):
    __tablename__='domain_email_outbox'
    id=Column(String,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    identity_token_id=Column(String,nullable=False)
    kind=Column(String,nullable=False)
    encrypted_payload=Column(String,nullable=False)
    delivery_status=Column(String,nullable=False,default='queued',index=True)
    attempts=Column(Integer,nullable=False,default=0)
    attempt_token=Column(Integer,nullable=False,default=0)
    worker_id=Column(String,nullable=True)
    lease_expires_at=Column(DateTime(timezone=True),nullable=True)
    created_at=Column(DateTime(timezone=True),nullable=False,default=now)
    sent_at=Column(DateTime(timezone=True),nullable=True)
    __table_args__=(UniqueConstraint('tenant_id','id'),
        ForeignKeyConstraint(['tenant_id','identity_token_id'],['domain_identity_tokens.tenant_id','domain_identity_tokens.id']))


class IdentityRateLimit(Base):
    # Anonymous authentication budgets contain only HMAC keys, never tenant records/email/IP values.
    # Direct access is denied; a narrow definer function updates counters atomically.
    __tablename__='identity_rate_limits'
    key_hash=Column(String,primary_key=True)
    window_start=Column(DateTime(timezone=True),nullable=False)
    attempts=Column(Integer,nullable=False)


# The tables below reference domain_drivers; load its model so any entry point that imports identity alone can still flush.
from app.domain.workforce import models as _driver_models  # noqa: E402,F401
