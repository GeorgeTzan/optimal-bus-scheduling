import uuid
from dataclasses import asdict
from datetime import datetime, date, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.domain.scheduling.models import (
    SchedulingPeriod,
    ScheduleRevision,
    RevisionAssignment,
    ApprovalRequest,
    Publication,
    SchedulingAuditLog,
)
from app.domain.scheduling.publication import (
    StaleVersionConflictError,
    ImmutableRevisionError,
    LockedAssignmentError,
    PublicationVerificationFailedError,
)
from app.domain.optimization.contracts import SolverProblem, Assignment
from app.domain.verification.verifier import HardRuleVerifier


class SchedulingService:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.verifier = HardRuleVerifier()

    def _log_audit(self, revision_id: str, action: str, actor: str, details: Optional[Dict[str, Any]] = None):
        log = SchedulingAuditLog(
            tenant_id=self.tenant_id,
            revision_id=revision_id,
            action=action,
            actor=actor,
            details=details or {},
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(log)
        self.db.flush()

    def create_period(self, name: str, start_date: date, end_date: date) -> SchedulingPeriod:
        period = SchedulingPeriod(
            tenant_id=self.tenant_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
        )
        self.db.add(period)
        self.db.commit()
        return period

    def create_revision(
        self,
        period_id: int,
        parent_revision_id: Optional[str] = None,
        author: str = "dispatcher",
        comment: Optional[str] = None,
    ) -> ScheduleRevision:
        rev_id = str(uuid.uuid4())
        rev = ScheduleRevision(
            revision_id=rev_id,
            tenant_id=self.tenant_id,
            period_id=period_id,
            parent_revision_id=parent_revision_id,
            version=1,
            status="draft",
            author=author,
            comment=comment,
        )
        self.db.add(rev)
        self.db.flush()

        if parent_revision_id:
            parent_assignments = (
                self.db.query(RevisionAssignment)
                .filter(
                    RevisionAssignment.tenant_id == self.tenant_id,
                    RevisionAssignment.revision_id == parent_revision_id,
                )
                .all()
            )
            for pa in parent_assignments:
                copied = RevisionAssignment(
                    tenant_id=self.tenant_id,
                    revision_id=rev_id,
                    trip_id=pa.trip_id,
                    resource_id=pa.resource_id,
                    start_minutes=pa.start_minutes,
                    end_minutes=pa.end_minutes,
                    start_station=pa.start_station,
                    end_station=pa.end_station,
                    is_locked=pa.is_locked,
                    is_cancelled=pa.is_cancelled,
                    cancellation_reason=pa.cancellation_reason,
                )
                self.db.add(copied)

        self._log_audit(rev_id, "create_revision", actor=author, details={"period_id": period_id, "parent": parent_revision_id})
        self.db.commit()
        return rev

    def get_revision(self, revision_id: str) -> Optional[ScheduleRevision]:
        return (
            self.db.query(ScheduleRevision)
            .filter(
                ScheduleRevision.tenant_id == self.tenant_id,
                ScheduleRevision.revision_id == revision_id,
            )
            .populate_existing().with_for_update().first()
        )

    def apply_assignment_patch(
        self,
        revision_id: str,
        patch: List[Dict[str, Any]],
        expected_version: int,
        actor: str = "dispatcher",
    ) -> ScheduleRevision:
        rev = self.get_revision(revision_id)
        if not rev:
            raise KeyError(f"Revision '{revision_id}' not found.")

        if rev.status == "published":
            raise ImmutableRevisionError(f"Revision '{revision_id}' is published and immutable.")

        if rev.version != expected_version:
            raise StaleVersionConflictError(
                f"Conflict: expected version {expected_version}, but current version is {rev.version}."
            )

        for item in patch:
            trip_id = str(item["trip_id"])
            existing = (
                self.db.query(RevisionAssignment)
                .filter(
                    RevisionAssignment.tenant_id == self.tenant_id,
                    RevisionAssignment.revision_id == revision_id,
                    RevisionAssignment.trip_id == trip_id,
                )
                .first()
            )

            if existing:
                if existing.is_cancelled:
                    raise ValueError("A cancelled trip cannot be edited through assignment patches.")
                if existing.is_locked and not item.get("unlock", False):
                    # Check if changing resource or timings
                    if existing.resource_id != item.get("resource_id", existing.resource_id):
                        raise LockedAssignmentError(
                            f"Trip '{trip_id}' is locked on resource '{existing.resource_id}'. Unlock before reassigning."
                        )

                existing.resource_id = item.get("resource_id", existing.resource_id)
                existing.start_minutes = item.get("start_minutes", existing.start_minutes)
                existing.end_minutes = item.get("end_minutes", existing.end_minutes)
                existing.start_station = item.get("start_station", existing.start_station)
                existing.end_station = item.get("end_station", existing.end_station)
                if "is_locked" in item:
                    existing.is_locked = bool(item["is_locked"])
            else:
                new_assign = RevisionAssignment(
                    tenant_id=self.tenant_id,
                    revision_id=revision_id,
                    trip_id=trip_id,
                    resource_id=str(item["resource_id"]),
                    start_minutes=int(item["start_minutes"]),
                    end_minutes=int(item["end_minutes"]),
                    start_station=str(item["start_station"]),
                    end_station=str(item["end_station"]),
                    is_locked=bool(item.get("is_locked", False)),
                )
                self.db.add(new_assign)

        rev.version += 1
        rev.status = "draft"
        for approval in self.db.query(ApprovalRequest).filter_by(tenant_id=self.tenant_id, revision_id=revision_id).filter(
            ApprovalRequest.status.in_(["pending", "approved"])):
            approval.status = "rejected"
        rev.updated_at = datetime.now(timezone.utc)

        self._log_audit(revision_id, "patch_assignments", actor=actor, details={"items_count": len(patch), "new_version": rev.version})
        self.db.commit()
        return rev

    def request_publication(self, revision_id: str, actor: str = "dispatcher") -> ApprovalRequest:
        rev = self.get_revision(revision_id)
        if not rev:
            raise KeyError(f"Revision '{revision_id}' not found.")

        if rev.status == "published":
            raise ImmutableRevisionError("Published revisions are immutable")

        req_id = str(uuid.uuid4())
        req = ApprovalRequest(
            request_id=req_id,
            tenant_id=self.tenant_id,
            revision_id=revision_id,
            requested_by=actor,
            status="pending",
        )
        self.db.add(req)
        rev.status = "approval_requested"
        self._log_audit(revision_id, "request_publication", actor=actor, details={"request_id": req_id})
        self.db.commit()
        return req

    def approve_publication(
        self,
        revision_id: str,
        actor: str = "operations_chief",
        comment: Optional[str] = None,
    ) -> ApprovalRequest:
        req = (
            self.db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.tenant_id == self.tenant_id,
                ApprovalRequest.revision_id == revision_id,
                ApprovalRequest.status == "pending",
            )
            .first()
        )
        if not req:
            raise KeyError(f"No pending approval request found for revision '{revision_id}'.")

        req.status = "approved"
        req.reviewer = actor
        req.review_comment = comment
        req.reviewed_at = datetime.now(timezone.utc)

        rev = self.get_revision(revision_id)
        if rev:
            rev.status = "approved"

        self._log_audit(revision_id, "approve_publication", actor=actor, details={"request_id": req.request_id, "comment": comment})
        self.db.commit()
        return req

    def publish_verified_revision(
        self,
        revision_id: str,
        actor: str = "dispatcher",
        problem: Optional[SolverProblem] = None,
    ) -> Publication:
        rev = self.get_revision(revision_id)
        if not rev:
            raise KeyError(f"Revision '{revision_id}' not found.")

        if rev.status == "published":
            raise ImmutableRevisionError("Published revisions are immutable")
        if problem is None or str(problem.tenant_id) != str(self.tenant_id):
            raise PublicationVerificationFailedError("An authoritative tenant problem is required")
        if rev.status != "approved":
            raise PublicationVerificationFailedError("An approved revision is required")

        assignments_db = (
            self.db.query(RevisionAssignment)
            .filter(
                RevisionAssignment.tenant_id == self.tenant_id,
                RevisionAssignment.revision_id == revision_id,
            )
            .all()
        )

        contracts_assignments = [
            Assignment(
                resource_id=a.resource_id,
                trip_id=a.trip_id,
                start_minutes=a.start_minutes,
                end_minutes=a.end_minutes,
                start_station=a.start_station,
                end_station=a.end_station,
            )
            for a in assignments_db if not a.is_cancelled and a.resource_id != "UNASSIGNED"
        ]

        # Verify through independent verifier
        if problem:
            report = self.verifier.verify(problem, contracts_assignments)
            if not report.is_feasible:
                raise PublicationVerificationFailedError(
                    f"Publication rejected: verification failed with {len(report.violations)} violations."
                )
            report_dict = {
                "valid": report.valid,
                "rule_version": report.rule_version,
                "violations_count": len(report.violations),
            }

        pub_id = str(uuid.uuid4())
        pub = Publication(
            publication_id=pub_id,
            tenant_id=self.tenant_id,
            revision_id=revision_id,
            published_by=actor,
            verification_report=report_dict,
        )
        self.db.add(pub)
        rev.status = "published"

        self._log_audit(revision_id, "publish_verified_revision", actor=actor, details={"publication_id": pub_id})
        self.db.commit()
        return pub

    def get_audit_trail(self, revision_id: str) -> List[SchedulingAuditLog]:
        return (
            self.db.query(SchedulingAuditLog)
            .filter(
                SchedulingAuditLog.tenant_id == self.tenant_id,
                SchedulingAuditLog.revision_id == revision_id,
            )
            .order_by(SchedulingAuditLog.timestamp.asc())
            .all()
        )
