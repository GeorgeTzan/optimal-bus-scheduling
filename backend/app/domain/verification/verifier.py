"""
Independent Verifier Implementation.
Derives validation directly from the canonical problem snapshot and assignment records.
"""

from __future__ import annotations
from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING, Sequence

from app.domain.optimization.availability import availability_allows_transition, availability_allows_trip
from app.domain.optimization.contracts import SolverProblem, Assignment, SolverResult
from app.domain.verification.rules import (
    RuleSet,
    VerificationReport,
    Violation,
    Severity,
)
from app.domain.workrules.draft import draft_duties
from app.domain.workrules.evaluate import evaluate
from app.domain.workrules.findings import WorkRuleFinding, caused_by

if TYPE_CHECKING:
    from app.domain.workrules.loader import WorkContext

FOCUS_DAYS = 7


class HardRuleVerifier:
    def __init__(self, rules: RuleSet | None = None):
        self.rules = rules or RuleSet()

    def verify(
        self, problem: SolverProblem, result: SolverResult | Sequence[Assignment], work: WorkContext | None = None
    ) -> VerificationReport:
        assignments = result.assignments if hasattr(result, "assignments") else result
        return verify_schedule(problem, assignments, self.rules, work)


def _work_violation(finding: WorkRuleFinding, severity: Severity, preexisting: bool, draft_day) -> Violation:
    measured = "" if finding.measured is None else f" (measured {finding.measured}, limit {finding.limit})"
    if preexisting:
        message = f"Existing issue on {finding.service_date}: {finding.rule_id} for driver {finding.driver_id}{measured}."
    elif finding.service_date != draft_day:
        message = f"{finding.rule_id} for driver {finding.driver_id} on {finding.service_date}{measured} is caused by the {draft_day} draft."
    else:
        message = f"{finding.rule_id} for driver {finding.driver_id} on {finding.service_date}{measured}."
    return Violation(
        rule_id=finding.rule_id,
        rule_name=finding.message_key,
        severity=severity,
        message=message,
        entity_type="Driver",
        entity_ids=[finding.driver_id, *finding.trip_ids],
        finding_key=finding.key,
        measured=finding.measured,
        limit=finding.limit,
        source=finding.source,
        hint=dict(finding.hint),
        message_key=finding.message_key,
        service_date=finding.service_date.isoformat(),
        preexisting=preexisting,
        kind=finding.kind,
    )


def work_violations(problem: SolverProblem, assignments: Sequence[Assignment], work: WorkContext) -> list[Violation]:
    day = work.service_date
    focus = (day, day + timedelta(days=FOCUS_DAYS))
    out: list[Violation] = []
    for driver_id, duty in sorted(draft_duties(work, problem, assignments).items()):
        timeline = work.timelines.get(driver_id)
        if timeline is None:
            continue
        with_draft = evaluate(timeline.with_day(day, duty), work.policy, focus, work.transfer_minutes, tz=work.tz)
        without_draft = evaluate(timeline.with_day(day, None), work.policy, focus, work.transfer_minutes, tz=work.tz)
        caused = {id(f) for f in caused_by(with_draft, without_draft)}
        for finding in with_draft:
            new = id(finding) in caused
            if finding.kind == "legal":
                out.append(_work_violation(finding, Severity.ERROR if new else Severity.WARNING, not new, day))
            elif finding.kind == "warning":
                if finding.key not in work.overrides:
                    out.append(_work_violation(finding, Severity.WARNING, not new, day))
            else:
                out.append(_work_violation(finding, Severity.INFO, False, day))
    return out


def verify_schedule(
    problem: SolverProblem,
    assignments: Sequence[Assignment],
    rules: RuleSet | None = None,
    work: WorkContext | None = None,
) -> VerificationReport:
    if rules is None:
        rules = RuleSet()

    violations: list[Violation] = []
    total_trips = len(problem.trips)
    problem_trip_map = {t.id: t for t in problem.trips}

    resources = {r.resource_id: r for r in problem.resources}
    for a in assignments:
        trip = problem_trip_map.get(a.trip_id)
        resource = resources.get(a.resource_id)
        if trip is None or resource is None:
            violations.append(Violation(
                rule_id="RULE_KNOWN_TRIP" if trip is None else "RULE_KNOWN_RESOURCE",
                rule_name="Known assignment entities", severity=Severity.ERROR,
                message=f"Unknown trip or resource in assignment {a.trip_id}/{a.resource_id}",
                entity_type="Trip", entity_ids=[a.trip_id]))
        elif resource.bus_type not in trip.allowed_bus_types:
            violations.append(Violation(
                rule_id="RULE_BUS_ELIGIBILITY", rule_name="Bus type eligibility", severity=Severity.ERROR,
                message=f"Trip {trip.id} requires bus types {trip.allowed_bus_types}; resource {resource.resource_id} has {resource.bus_type}.",
                entity_type="Trip", entity_ids=[trip.id]))

    # Candidate/assignment metadata never overrides immutable authoritative trip inputs.
    canonical_assignments=[]
    for supplied in assignments:
        trip=problem_trip_map.get(supplied.trip_id)
        if trip is None:
            canonical_assignments.append(supplied)
            continue
        canonical=Assignment(supplied.resource_id,trip.id,trip.start_minutes,trip.end_minutes,
                             trip.start_station,trip.end_station)
        if supplied!=canonical:
            violations.append(Violation(
                rule_id="RULE_ASSIGNMENT_SNAPSHOT",rule_name="Authoritative trip details",severity=Severity.ERROR,
                message=f"Trip {trip.id} has times or stations that differ from its immutable schedule input.",
                entity_type="Trip",entity_ids=[trip.id]))
        canonical_assignments.append(canonical)
    assignments=canonical_assignments

    # Availability is recomputed from the frozen windows only; a solver's own eligibility flag is never trusted.
    if problem.availability_enforced:
        exempt = set(problem.availability_exempt_trip_ids)
        by_resource = defaultdict(list)
        for a in assignments:
            if a.trip_id in problem_trip_map and a.resource_id in resources and a.trip_id not in exempt:
                by_resource[a.resource_id].append(problem_trip_map[a.trip_id])
        for resource_id, trips in by_resource.items():
            resource = resources[resource_id]
            if resource.available_windows is None:
                violations.append(Violation(rule_id="RULE_AVAILABILITY_UNKNOWN", rule_name="Working time must be known", severity=Severity.ERROR,
                    message=f"Resource '{resource_id}' has no confirmed working time for this day.", entity_type="Resource", entity_ids=[resource_id]))
                continue
            ordered = sorted(trips, key=lambda t: (t.start_minutes, t.end_minutes))
            for t in ordered:
                if not availability_allows_trip(resource, t):
                    violations.append(Violation(rule_id="RULE_AVAILABILITY_TRIP", rule_name="Driver and vehicle availability", severity=Severity.ERROR,
                        message=f"Trip '{t.id}' falls outside the confirmed availability of resource '{resource_id}'.", entity_type="Trip", entity_ids=[t.id, resource_id]))
            for previous, following in zip(ordered, ordered[1:]):
                if previous.end_station == following.start_station:
                    continue
                try:
                    needed = problem.transfer_matrix[problem.stations.index(previous.end_station)][problem.stations.index(following.start_station)]
                except (ValueError, IndexError, TypeError):
                    continue  # an unknown transfer is reported by the continuity rule
                if type(needed) is int and not availability_allows_transition(resource, previous, following, needed):
                    violations.append(Violation(rule_id="RULE_AVAILABILITY_TRANSITION", rule_name="Travel inside available time", severity=Severity.ERROR,
                        message=f"Resource '{resource_id}' cannot complete the {needed}m transfer between '{previous.id}' and '{following.id}' within one available window.",
                        entity_type="Resource", entity_ids=[resource_id, previous.id, following.id]))

    # 1. Check duplicate trip assignments
    trip_to_resources = defaultdict(list)
    for a in assignments:
        trip_to_resources[a.trip_id].append(a.resource_id)

    if rules.enforce_unique_trips:
        for trip_id, assigned_to in trip_to_resources.items():
            if len(assigned_to) > 1:
                violations.append(
                    Violation(
                        rule_id="RULE_UNIQUE_TRIP",
                        rule_name="Unique Trip Assignment",
                        severity=Severity.ERROR,
                        message=f"Trip '{trip_id}' is assigned to multiple resources: {assigned_to}",
                        entity_type="Trip",
                        entity_ids=[trip_id],
                    )
                )

    # 2. Check resource-level temporal overlap and continuity
    resource_assignments = defaultdict(list)
    for a in assignments:
        resource_assignments[a.resource_id].append(a)

    for resource_id, res_assignments in resource_assignments.items():
        # Sort by start_minutes
        sorted_trips = sorted(res_assignments, key=lambda x: (x.start_minutes, x.end_minutes))

        for i in range(len(sorted_trips) - 1):
            curr = sorted_trips[i]
            nxt = sorted_trips[i + 1]

            # Temporal overlap check
            if rules.enforce_no_temporal_overlap:
                if curr.end_minutes > nxt.start_minutes:
                    violations.append(
                        Violation(
                            rule_id="RULE_NO_TEMPORAL_OVERLAP",
                            rule_name="No Temporal Overlap",
                            severity=Severity.ERROR,
                            message=(
                                f"Resource '{resource_id}' has overlapping trips: "
                                f"Trip '{curr.trip_id}' ends at {curr.end_minutes}m, but "
                                f"Trip '{nxt.trip_id}' starts at {nxt.start_minutes}m."
                            ),
                            entity_type="Resource",
                            entity_ids=[resource_id, curr.trip_id, nxt.trip_id],
                        )
                    )

            # Station continuity check
            if rules.enforce_station_continuity:
                if curr.end_station != nxt.start_station:
                    # Transfer needed: check if transfer time fits
                    transfer_time = None
                    if problem.stations and problem.transfer_matrix:
                        try:
                            from_idx = problem.stations.index(curr.end_station)
                            to_idx = problem.stations.index(nxt.start_station)
                            transfer_time = problem.transfer_matrix[from_idx][to_idx]
                        except (ValueError, IndexError, TypeError):
                            pass
                    if type(transfer_time) is not int or transfer_time<0:
                        violations.append(Violation(
                            rule_id="RULE_UNKNOWN_TRANSFER",rule_name="Verified transfer duration",severity=Severity.ERROR,
                            message=f"Enter a verified transfer duration from {curr.end_station} to {nxt.start_station}.",
                            entity_type="Resource",entity_ids=[resource_id,curr.trip_id,nxt.trip_id]))
                        continue

                    available_gap = nxt.start_minutes - curr.end_minutes
                    if available_gap < transfer_time:
                        violations.append(
                            Violation(
                                rule_id="RULE_STATION_CONTINUITY",
                                rule_name="Station Continuity and Deadhead Feasibility",
                                severity=Severity.ERROR,
                                message=(
                                    f"Resource '{resource_id}' moves from {curr.end_station} to {nxt.start_station} "
                                    f"requiring {transfer_time}m transfer, but only {available_gap}m available."
                                ),
                                entity_type="Resource",
                                entity_ids=[resource_id, curr.trip_id, nxt.trip_id],
                            )
                        )

    # A resource is a driver/vehicle pair. Different pair IDs may still share
    # the same person or vehicle; check their authoritative identities too.
    identity_groups = {"driver": defaultdict(list), "vehicle": defaultdict(list)}
    missing_identity = set()
    for assignment in assignments:
        resource = resources.get(assignment.resource_id)
        if resource is None:
            continue
        for kind, identity in (("driver", resource.driver_id), ("vehicle", resource.bus_id)):
            if not isinstance(identity, str) or not identity.strip():
                key = (resource.resource_id, kind)
                if key not in missing_identity:
                    missing_identity.add(key)
                    violations.append(Violation(
                        rule_id="RULE_RESOURCE_IDENTITY", rule_name="Known resource identity",
                        severity=Severity.ERROR,
                        message=f"Resource '{resource.resource_id}' has no verified {kind} identity.",
                        entity_type="Resource", entity_ids=[resource.resource_id],
                    ))
                continue
            identity_groups[kind][identity].append(assignment)
    if rules.enforce_no_temporal_overlap:
        for kind, groups in identity_groups.items():
            for identity, rows in groups.items():
                active = []
                for current in sorted(rows, key=lambda item: (item.start_minutes, item.end_minutes, item.trip_id)):
                    active = [item for item in active if item.end_minutes > current.start_minutes]
                    other = next((item for item in active if item.resource_id != current.resource_id), None)
                    if other:
                        violations.append(Violation(
                            rule_id="RULE_DRIVER_OVERLAP" if kind == "driver" else "RULE_VEHICLE_OVERLAP",
                            rule_name=f"No overlapping {kind} assignments", severity=Severity.ERROR,
                            message=f"The same {kind} has overlapping trips '{other.trip_id}' and '{current.trip_id}' on different pairings.",
                            entity_type=kind.title(), entity_ids=[identity, other.trip_id, current.trip_id],
                        ))
                    active.append(current)

    # The same vehicle or driver can continue under a different pairing.
    # Empty-bus transfer durations do not establish how a driver travels
    # between different vehicles, so unknown driver relocation is blocked.
    if rules.enforce_station_continuity:
        for kind, groups in identity_groups.items():
            for identity, rows in groups.items():
                ordered=sorted(rows,key=lambda item:(item.start_minutes,item.end_minutes,item.trip_id))
                for previous,current in zip(ordered,ordered[1:]):
                    if previous.resource_id==current.resource_id or previous.end_minutes>current.start_minutes or previous.end_station==current.start_station:
                        continue
                    if kind=='driver':
                        violations.append(Violation(rule_id='RULE_DRIVER_RELOCATION_UNCONFIRMED',rule_name='Driver relocation requires review',severity=Severity.ERROR,
                            message='The driver changes pairings at different stations; their relocation is not verified.',
                            entity_type='Driver',entity_ids=[identity,previous.trip_id,current.trip_id]))
                        continue
                    duration=None
                    if problem.stations and problem.transfer_matrix:
                        try:duration=problem.transfer_matrix[problem.stations.index(previous.end_station)][problem.stations.index(current.start_station)]
                        except (ValueError,IndexError,TypeError):pass
                    if type(duration) is not int or duration<0 or current.start_minutes-previous.end_minutes<duration:
                        violations.append(Violation(rule_id='RULE_VEHICLE_CONTINUITY',rule_name='Vehicle transfer feasibility',severity=Severity.ERROR,
                            message='The vehicle cannot be verified to reach its next trip between pairings.',
                            entity_type='Vehicle',entity_ids=[identity,previous.trip_id,current.trip_id]))
                        continue
                    # The empty transfer needs a driver: one of the two crews must be working while it happens.
                    if problem.availability_enforced and previous.trip_id not in exempt and current.trip_id not in exempt:
                        crews=[resources.get(previous.resource_id),resources.get(current.resource_id)]
                        if all(crew is not None and crew.available_windows is not None for crew in crews) and not any(availability_allows_transition(crew,previous,current,duration) for crew in crews):
                            violations.append(Violation(rule_id='RULE_AVAILABILITY_TRANSITION',rule_name='Travel inside available time',severity=Severity.ERROR,
                                message=f"The vehicle needs {duration}m to move between '{previous.trip_id}' and '{current.trip_id}', and neither crew is working then.",
                                entity_type='Vehicle',entity_ids=[identity,previous.trip_id,current.trip_id]))

    # 3. Check mandatory chains
    if rules.enforce_mandatory_chains:
        # Build trip-to-resource mapping for single-assigned trips
        trip_resource_map = {a.trip_id: a.resource_id for a in assignments}

        for chain in problem.chains:
            chain_trips = chain.trip_ids
            assigned_resources = {trip_resource_map.get(tid) for tid in chain_trips}

            # If any trip in chain is unassigned or assigned to different resources
            if None in assigned_resources or len(assigned_resources) > 1:
                violations.append(
                    Violation(
                        rule_id="RULE_MANDATORY_CHAIN",
                        rule_name="Mandatory Chain Integrity",
                        severity=Severity.ERROR,
                        message=(
                            f"Mandatory chain {chain_trips} is broken or split across resources: {assigned_resources}"
                        ),
                        entity_type="Chain",
                        entity_ids=list(chain_trips),
                    )
                )

    # 4. Coverage calculation
    assigned_trip_ids = {a.trip_id for a in assignments if a.trip_id in problem_trip_map}
    unassigned_trips = [t.id for t in problem.trips if t.id not in assigned_trip_ids]
    coverage_percent = (
        (len(assigned_trip_ids) / total_trips * 100.0) if total_trips > 0 else 100.0
    )

    if rules.require_full_coverage and unassigned_trips:
        violations.append(
            Violation(
                rule_id="RULE_REQUIRED_COVERAGE",
                rule_name="Full Trip Coverage Required",
                severity=Severity.ERROR,
                message=f"Schedule has {len(unassigned_trips)} unassigned trips, but full coverage is required.",
                entity_type="Problem",
                entity_ids=unassigned_trips,
            )
        )

    if work is not None:
        violations.extend(work_violations(problem, assignments, work))

    is_valid = not any(v.severity == Severity.ERROR for v in violations)

    return VerificationReport(
        valid=is_valid,
        rule_version=rules.version if work is None else f"{rules.version}+{work.policy.legal_version}+company-v{work.policy.company_version}",
        violations=violations,
        coverage_percent=round(coverage_percent, 2),
        unassigned_trips=unassigned_trips,
        assigned_trips_count=len(assigned_trip_ids),
        total_trips_count=total_trips,
    )
