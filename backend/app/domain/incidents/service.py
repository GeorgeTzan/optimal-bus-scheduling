from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.domain.incidents.models import Incident, RecoveryProposal
from app.domain.scheduling.models import RevisionAssignment


class IncidentService:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def report_incident(
        self,
        incident_type: str,
        resource_id: Optional[str],
        trip_id: Optional[str],
        description: str,
        reported_by: str,
    ) -> Incident:
        incident = Incident(
            tenant_id=self.tenant_id,
            incident_type=incident_type,
            resource_id=resource_id,
            trip_id=trip_id,
            description=description,
            reported_by=reported_by,
            status="open",
        )
        self.db.add(incident)
        self.db.commit()
        return incident

    def propose_recovery(
        self,
        incident_id: int,
        as_of_minutes: int,
        reassignments: List[Dict[str, Any]],
    ) -> RecoveryProposal:
        proposal = RecoveryProposal(
            tenant_id=self.tenant_id,
            incident_id=incident_id,
            as_of_minutes=as_of_minutes,
            reassignments=reassignments,
            status="pending_approval",
        )
        self.db.add(proposal)
        self.db.commit()
        return proposal

    def approve_recovery(
        self,
        proposal_id: int,
        actor: str,
        user_role: str = "dispatcher",
    ) -> RecoveryProposal:
        if user_role not in ("dispatcher", "admin", "chief_dispatcher"):
            raise PermissionError("Only authorized dispatchers or admins can approve disruption recovery.")

        proposal = (
            self.db.query(RecoveryProposal)
            .filter(
                RecoveryProposal.tenant_id == self.tenant_id,
                RecoveryProposal.id == proposal_id,
            )
            .first()
        )
        if not proposal:
            raise KeyError(f"Recovery proposal '{proposal_id}' not found.")

        proposal.status = "approved"
        proposal.approved_by = actor
        proposal.approved_at = datetime.now(timezone.utc)

        # Mark parent incident resolving
        incident = self.db.query(Incident).filter(Incident.id == proposal.incident_id).first()
        if incident:
            incident.status = "resolved"
            incident.resolved_at = datetime.now(timezone.utc)

        self.db.commit()
        return proposal

    def get_driver_duties(
        self,
        revision_id: str,
        driver_resource_id: str,
    ) -> List[RevisionAssignment]:
        """
        Enforces strict own-duty-only visibility for driver roles.
        """
        return (
            self.db.query(RevisionAssignment)
            .filter(
                RevisionAssignment.tenant_id == self.tenant_id,
                RevisionAssignment.revision_id == revision_id,
                RevisionAssignment.resource_id == driver_resource_id,
            )
            .order_by(RevisionAssignment.start_minutes.asc())
            .all()
        )
