from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, DateTime, Date, JSON, UniqueConstraint, ForeignKeyConstraint, CheckConstraint, Index, text
from sqlalchemy.orm import relationship

from db.database import Base


class Station(Base):
    version = Column(Integer, nullable=False, default=1)
    external_source = Column(String, nullable=True)
    external_key = Column(String, nullable=True)
    __tablename__ = "domain_stations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    code = Column(String, index=True, nullable=False)
    name_el = Column(String, nullable=False)
    name_en = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_depot = Column(Boolean, default=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)


class Route(Base):
    __tablename__ = "domain_routes"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    origin_station_id = Column(Integer, ForeignKey("domain_stations.id"), nullable=False)
    destination_station_id = Column(Integer, ForeignKey("domain_stations.id"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    external_source = Column(String, nullable=True)
    external_key = Column(String, nullable=True)
    distance_km = Column(Float, nullable=True, default=None)
    typical_duration_minutes = Column(Integer, nullable=True, default=None)

    origin = relationship("Station", foreign_keys=[origin_station_id])
    destination = relationship("Station", foreign_keys=[destination_station_id])


class ServiceTemplate(Base):
    version = Column(Integer, nullable=False, default=1)
    external_source = Column(String, nullable=True)
    external_key = Column(String, nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    operating_weekdays = Column(JSON, nullable=True)
    arrival_day_offset = Column(Integer, nullable=True)
    allowed_bus_types = Column(JSON, nullable=True)
    __tablename__ = "domain_service_templates"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    route_id = Column(Integer, ForeignKey("domain_routes.id"), nullable=False)
    trip_code = Column(String, index=True, nullable=False)
    departure_time = Column(String, nullable=False)  # HH:MM local
    arrival_time = Column(String, nullable=False)  # HH:MM local
    is_active = Column(Boolean, default=True)

    route = relationship("Route")


class TripInstance(Base):
    __tablename__ = "domain_trip_instances"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), index=True, nullable=False)
    trip_code = Column(String, index=True, nullable=False)
    service_date = Column(Date, index=True, nullable=False)
    origin_station_id = Column(Integer, ForeignKey("domain_stations.id"), nullable=False)
    destination_station_id = Column(Integer, ForeignKey("domain_stations.id"), nullable=False)
    source_hash = Column(String, nullable=True)
    template_version = Column(Integer, nullable=True)
    calendar_exception_version = Column(Integer, nullable=True)
    start_utc = Column(DateTime(timezone=True), nullable=False)
    end_utc = Column(DateTime(timezone=True), nullable=False)
    template_id = Column(Integer, ForeignKey("domain_service_templates.id"), nullable=True)
    properties = Column(JSON, default=dict)

    origin = relationship("Station", foreign_keys=[origin_station_id])
    destination = relationship("Station", foreign_keys=[destination_station_id])
    template = relationship("ServiceTemplate")


class ServiceException(Base):
    __tablename__='domain_service_exceptions'
    id=Column(Integer,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    template_id=Column(Integer,nullable=False,index=True)
    service_date=Column(Date,nullable=False,index=True)
    action=Column(String,nullable=False)
    departure_time=Column(String,nullable=True)
    arrival_time=Column(String,nullable=True)
    arrival_day_offset=Column(Integer,nullable=True)
    fold_start=Column(Integer,nullable=True)
    fold_end=Column(Integer,nullable=True)
    version=Column(Integer,nullable=False,default=1)
    __table_args__=(UniqueConstraint('tenant_id','id'),UniqueConstraint('tenant_id','template_id','service_date'),
        ForeignKeyConstraint(['tenant_id','template_id'],['domain_service_templates.tenant_id','domain_service_templates.id']),
        CheckConstraint("action IN ('inherit','run','cancel')"),CheckConstraint('version>0'),
        CheckConstraint('arrival_day_offset IS NULL OR arrival_day_offset BETWEEN 0 AND 2'),
        CheckConstraint('fold_start IS NULL OR fold_start IN (0,1)'),CheckConstraint('fold_end IS NULL OR fold_end IN (0,1)'))


class DailyPairing(Base):
    __tablename__='domain_daily_pairings'
    id=Column(Integer,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    service_date=Column(Date,nullable=False,index=True)
    driver_id=Column(Integer,nullable=False)
    vehicle_id=Column(Integer,nullable=False)
    home_station_id=Column(Integer,nullable=False)
    is_active=Column(Boolean,nullable=False,default=True)
    is_confirmed=Column(Boolean,nullable=False,default=False)
    confirmed_source_hash=Column(String,nullable=True)
    confirmed_sources=Column(JSON,nullable=True)
    confirmed_by=Column(Integer,nullable=True)
    confirmed_at=Column(DateTime(timezone=True),nullable=True)
    version=Column(Integer,nullable=False,default=1)
    created_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    __table_args__=(UniqueConstraint('tenant_id','id'),
        ForeignKeyConstraint(['tenant_id','driver_id'],['domain_drivers.tenant_id','domain_drivers.id']),
        ForeignKeyConstraint(['tenant_id','vehicle_id'],['domain_vehicles.tenant_id','domain_vehicles.id']),
        ForeignKeyConstraint(['tenant_id','home_station_id'],['domain_stations.tenant_id','domain_stations.id']),
        ForeignKeyConstraint(['tenant_id','confirmed_by'],['users.ktel_id','users.id']),CheckConstraint('version>0'),
        CheckConstraint('NOT is_confirmed OR (confirmed_source_hash IS NOT NULL AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)'),
        Index('uq_daily_pair_driver','tenant_id','service_date','driver_id',unique=True,postgresql_where=text('is_active'),sqlite_where=text('is_active=1')),
        Index('uq_daily_pair_vehicle','tenant_id','service_date','vehicle_id',unique=True,postgresql_where=text('is_active'),sqlite_where=text('is_active=1')))


class StationTransfer(Base):
    __tablename__='domain_station_transfers'
    id=Column(Integer,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    origin_station_id=Column(Integer,nullable=False)
    destination_station_id=Column(Integer,nullable=False)
    minutes=Column(Integer,nullable=False)
    confirmed_source_hash=Column(String,nullable=False)
    source_note=Column(String,nullable=True)
    version=Column(Integer,nullable=False,default=1)
    confirmed_by=Column(Integer,nullable=False)
    confirmed_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    __table_args__=(UniqueConstraint('tenant_id','id'),UniqueConstraint('tenant_id','origin_station_id','destination_station_id'),
        ForeignKeyConstraint(['tenant_id','origin_station_id'],['domain_stations.tenant_id','domain_stations.id']),
        ForeignKeyConstraint(['tenant_id','destination_station_id'],['domain_stations.tenant_id','domain_stations.id']),
        ForeignKeyConstraint(['tenant_id','confirmed_by'],['users.ktel_id','users.id']),
        CheckConstraint('minutes BETWEEN 0 AND 1440'),CheckConstraint('version>0'),CheckConstraint('origin_station_id<>destination_station_id'))


class ServiceConnection(Base):
    __tablename__='domain_service_connections'
    id=Column(Integer,primary_key=True)
    tenant_id=Column(Integer,ForeignKey('ktels.id'),nullable=False,index=True)
    incoming_template_id=Column(Integer,nullable=False)
    outgoing_template_id=Column(Integer,nullable=False)
    is_active=Column(Boolean,nullable=False,default=True)
    version=Column(Integer,nullable=False,default=1)
    created_by=Column(Integer,nullable=True)
    updated_by=Column(Integer,nullable=True)
    created_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    updated_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    __table_args__=(UniqueConstraint('tenant_id','id'),UniqueConstraint('tenant_id','incoming_template_id','outgoing_template_id'),
        ForeignKeyConstraint(['tenant_id','incoming_template_id'],['domain_service_templates.tenant_id','domain_service_templates.id']),
        ForeignKeyConstraint(['tenant_id','outgoing_template_id'],['domain_service_templates.tenant_id','domain_service_templates.id']),
        ForeignKeyConstraint(['tenant_id','created_by'],['users.ktel_id','users.id']),
        ForeignKeyConstraint(['tenant_id','updated_by'],['users.ktel_id','users.id']),
        CheckConstraint('incoming_template_id<>outgoing_template_id'),CheckConstraint('version>0'),
        Index('uq_service_connection_next','tenant_id','incoming_template_id',unique=True,postgresql_where=text('is_active'),sqlite_where=text('is_active=1')),
        Index('uq_service_connection_previous','tenant_id','outgoing_template_id',unique=True,postgresql_where=text('is_active'),sqlite_where=text('is_active=1')))
