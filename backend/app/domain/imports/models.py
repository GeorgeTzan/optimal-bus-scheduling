"""Tenant-owned staged imports, stable source identities and transactional audit."""

from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    JSON,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def json_type():
    return JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class UploadBatch(Base):
    __tablename__ = "domain_import_batches"
    batch_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(Integer, ForeignKey("ktels.id"), nullable=False, index=True)
    created_by = Column(Integer, nullable=False)
    updated_by = Column(Integer, nullable=False)
    original_filename = Column(String, nullable=False)
    file_format = Column(String, nullable=False)
    file_bytes = Column(Integer, nullable=False)
    checksum = Column(String(64), nullable=False)
    source_kind = Column(String, nullable=False)
    requested_entity = Column(String, nullable=False)
    schema_version = Column(String, nullable=False)
    validation_version = Column(
        String, nullable=False, default="ktel-import-validation-v1"
    )
    locale = Column(String, nullable=False)
    source_locale = Column(String, nullable=False)
    entities = Column(json_type(), nullable=False, default=list)
    status = Column(String, nullable=False, default="review")
    version = Column(Integer, nullable=False, default=1)
    row_count = Column(Integer, nullable=False, default=0)
    summary = Column(json_type(), nullable=False, default=dict)
    file_issues = Column(json_type(), nullable=False, default=list)
    source_snapshot = Column(json_type(), nullable=False, default=dict)
    station_resolutions = Column(json_type(), nullable=False, default=dict)
    station_plan = Column(json_type(), nullable=False, default=list)
    result_summary = Column(json_type(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    committed_at = Column(DateTime(timezone=True), nullable=True)
    raw_purged_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "batch_id"),
        ForeignKeyConstraint(
            ["tenant_id", "created_by"], ["users.ktel_id", "users.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "updated_by"], ["users.ktel_id", "users.id"]
        ),
        CheckConstraint(
            "status IN ('review','ready','committed','discarded','purged')"
        ),
        CheckConstraint("file_format IN ('xlsx','csv')"),
        CheckConstraint("locale IN ('en','el') AND source_locale IN ('en','el')"),
        CheckConstraint("version>0 AND row_count>=0 AND file_bytes>0"),
        CheckConstraint("length(checksum)=64"),
        CheckConstraint(
            "status<>'committed' OR (result_summary IS NOT NULL AND committed_at IS NOT NULL)"
        ),
        Index(
            "uq_import_active_source",
            "tenant_id",
            "checksum",
            "source_kind",
            "schema_version",
            unique=True,
            postgresql_where=text("status NOT IN ('discarded','purged')"),
            sqlite_where=text("status NOT IN ('discarded','purged')"),
        ),
        Index("ix_import_retention", "tenant_id", "expires_at", "raw_purged_at"),
    )


class UploadRow(Base):
    __tablename__ = "domain_import_rows"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), nullable=False, index=True)
    batch_id = Column(String, nullable=False, index=True)
    position = Column(Integer, nullable=False)
    entity = Column(String, nullable=False)
    sheet = Column(String, nullable=False)
    row_number = Column(Integer, nullable=False)
    raw = Column(json_type(), nullable=False)
    cell_types = Column(json_type(), nullable=False, default=dict)
    source_columns = Column(json_type(), nullable=False, default=dict)
    source_cells = Column(json_type(), nullable=False, default=dict)
    values = Column(json_type(), nullable=False, default=dict)
    issues = Column(json_type(), nullable=False, default=list)
    resolution = Column(json_type(), nullable=False, default=dict)
    planned_reference = Column(String, nullable=True)
    plan = Column(json_type(), nullable=False, default=dict)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "batch_id", "position"),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["domain_import_batches.tenant_id", "domain_import_batches.batch_id"],
        ),
        CheckConstraint("position>=0 AND row_number>=2"),
        CheckConstraint(
            "entity IN ('drivers','vehicles','stations','timetable','pairings','transfers','connections')"
        ),
    )


TARGET_COLUMNS = {
    "drivers": "driver_id",
    "vehicles": "vehicle_id",
    "stations": "station_id",
    "timetable": "template_id",
}


class ImportIdentity(Base):
    __tablename__ = "domain_import_identities"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), nullable=False, index=True)
    entity = Column(String, nullable=False)
    source = Column(String, nullable=False)
    external_key = Column(String, nullable=False)
    driver_id = Column(Integer, nullable=True)
    vehicle_id = Column(Integer, nullable=True)
    station_id = Column(Integer, nullable=True)
    template_id = Column(Integer, nullable=True)
    batch_id = Column(String, nullable=False)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "entity", "source", "external_key"),
        ForeignKeyConstraint(
            ["tenant_id", "driver_id"],
            ["domain_drivers.tenant_id", "domain_drivers.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "vehicle_id"],
            ["domain_vehicles.tenant_id", "domain_vehicles.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "station_id"],
            ["domain_stations.tenant_id", "domain_stations.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "template_id"],
            ["domain_service_templates.tenant_id", "domain_service_templates.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["domain_import_batches.tenant_id", "domain_import_batches.batch_id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "created_by"], ["users.ktel_id", "users.id"]
        ),
        CheckConstraint(
            """(entity='drivers' AND driver_id IS NOT NULL AND vehicle_id IS NULL AND station_id IS NULL AND template_id IS NULL)
          OR (entity='vehicles' AND vehicle_id IS NOT NULL AND driver_id IS NULL AND station_id IS NULL AND template_id IS NULL)
          OR (entity='stations' AND station_id IS NOT NULL AND driver_id IS NULL AND vehicle_id IS NULL AND template_id IS NULL)
          OR (entity='timetable' AND template_id IS NOT NULL AND driver_id IS NULL AND vehicle_id IS NULL AND station_id IS NULL)"""
        ),
    )

    @property
    def target_id(self):
        return getattr(self, TARGET_COLUMNS[self.entity])


class ImportAudit(Base):
    __tablename__ = "domain_import_audit"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("ktels.id"), nullable=False, index=True)
    batch_id = Column(String, nullable=False, index=True)
    actor_id = Column(Integer, nullable=True)
    actor_type = Column(String, nullable=False, default="user")
    event = Column(String, nullable=False)
    batch_version = Column(Integer, nullable=False)
    details = Column(json_type(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["domain_import_batches.tenant_id", "domain_import_batches.batch_id"],
        ),
        ForeignKeyConstraint(["tenant_id", "actor_id"], ["users.ktel_id", "users.id"]),
        CheckConstraint("actor_type IN ('user','retention')"),
        CheckConstraint("batch_version>0"),
        CheckConstraint("actor_type<>'user' OR actor_id IS NOT NULL"),
    )
