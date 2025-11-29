from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from db.database import Base


class KTEL(Base):
    __tablename__ = "ktels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    region = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    users = relationship("User", back_populates="ktel")
    schedules = relationship("Schedule", back_populates="ktel")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    ktel_id = Column(Integer, ForeignKey("ktels.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ktel = relationship("KTEL", back_populates="users")


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    date = Column(DateTime)
    status = Column(String, default="draft")
    ktel_id = Column(Integer, ForeignKey("ktels.id"))
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ktel = relationship("KTEL", back_populates="schedules")
    created_by = relationship("User")
    trips = relationship("Trip", back_populates="schedule")
    drivers = relationship("Driver", back_populates="schedule")
    solution = relationship("Solution", back_populates="schedule", uselist=False)


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    trip_code = Column(String, index=True)
    start_station = Column(String)
    end_station = Column(String)
    start_time = Column(String)
    end_time = Column(String)
    schedule_id = Column(Integer, ForeignKey("schedules.id"))
    properties = Column(JSON, default={})

    schedule = relationship("Schedule", back_populates="trips")


class Driver(Base):
    __tablename__ = "drivers"

    id = Column(Integer, primary_key=True, index=True)
    driver_code = Column(String, index=True)
    bus_id = Column(String)
    home_station = Column(String)
    schedule_id = Column(Integer, ForeignKey("schedules.id"))
    properties = Column(JSON, default={})

    schedule = relationship("Schedule", back_populates="drivers")


class Solution(Base):
    __tablename__ = "solutions"

    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), unique=True)
    assignments = Column(JSON)
    bus_states = Column(JSON)
    total_idle_time = Column(Integer)
    buses_used = Column(Integer)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    schedule = relationship("Schedule", back_populates="solution")
