"""Unpublished operational revisions must still match current driver and vehicle availability.
Published bases are exempt, so a recovery is never blocked by the absence it repairs."""
from datetime import datetime, timedelta
from app.domain.office.availability import availability_for_resources
from app.domain.scheduling.snapshots import decode_problem


def frozen_horizon(source: dict, problem) -> tuple[datetime, datetime]:
    """The span a draft was prepared for: its frozen availability horizon, or one derived from its trips for older drafts."""
    origin = datetime.fromisoformat(source["service_day_start_utc"])
    stored = (source.get("availability") or {}).get("end_utc")
    if stored:
        return origin, datetime.fromisoformat(stored)
    longest = max((value for row in problem.transfer_matrix for value in row), default=0)
    return origin, origin + timedelta(minutes=max((trip.end_minutes for trip in problem.trips), default=0) + longest)


def availability_review_required(db, revision, snapshot) -> bool:
    source = snapshot.source_data
    if revision.status == "published" or source.get("source") != "operational":
        return False
    stored = source.get("availability")
    if source.get("source_schema_version") != "ktel-operational-v2" or not stored:
        return True
    problem = decode_problem(snapshot.problem_data)
    keys = [(int(resource.driver_id), int(resource.bus_id)) for resource in problem.resources]
    found = availability_for_resources(db, revision.tenant_id, keys, datetime.fromisoformat(stored["start_utc"]), datetime.fromisoformat(stored["end_utc"]))
    frozen = stored.get("resources", {})
    return any(resource.resource_id not in frozen or found[key].fingerprint != frozen[resource.resource_id]["fingerprint"]
               for resource, key in zip(problem.resources, keys))
