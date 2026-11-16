from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Callable, Literal

from app.domain.workrules.policy import WorkRulePolicy
from app.domain.workrules.timeline import Duty, DriverProfile


@dataclass(frozen=True)
class Gap:
    start: datetime
    end: datetime
    kind: Literal["work", "break", "interruption"]


@dataclass(frozen=True)
class DutyFacts:
    start: datetime
    end: datetime
    work_minutes: int
    driving_minutes: int
    long_route_driving_minutes: int
    overtime_minutes: int
    gaps: tuple[Gap, ...]
    longest_driving_without_break: int
    urban: bool
    urban_break_taken: bool
    interruptions: int
    interruption_minutes: int
    ends_away_from_base: bool
    longest_run_start: datetime | None = None


def _minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def _classify(minutes: int, policy: WorkRulePolicy) -> Literal["work", "break", "interruption"]:
    if minutes < policy.value("break_piece_threshold"):
        return "work"
    if minutes <= policy.value("interruption_threshold"):
        return "break"
    return "interruption"


def split_duty(duty: Duty, policy: WorkRulePolicy) -> tuple[Duty, ...]:
    reduced = policy.value("daily_rest_reduced")
    check, out, back = policy.value("vehicle_check"), policy.value("dead_run_out"), policy.value("dead_run_back")
    parts: list[list] = []
    for trip in duty.trips:
        if parts:
            last = parts[-1][-1]
            rest = _minutes(trip.start - last.end) - check
            rest -= (0 if last.destination_is_depot else back) + (0 if trip.origin_is_depot else out)
            if rest >= reduced:
                parts.append([trip])
                continue
            parts[-1].append(trip)
        else:
            parts.append([trip])
    if len(parts) <= 1:
        return (duty,)
    return tuple(replace(duty, trips=tuple(part)) for part in parts)


def duty_parts(
    duties, profile: DriverProfile, policy: WorkRulePolicy, transfer_minutes: Callable[[str, str], int | None]
) -> list[tuple[Duty, DutyFacts]]:
    return [
        (part, duty_facts(part, profile, policy, transfer_minutes))
        for duty in duties
        if duty.trips
        for part in split_duty(duty, policy)
    ]


def duty_facts(
    duty: Duty,
    profile: DriverProfile,
    policy: WorkRulePolicy,
    transfer_minutes: Callable[[str, str], int | None],
) -> DutyFacts:
    trips = duty.trips
    first, last = trips[0], trips[-1]
    dead_out = 0 if first.origin_is_depot else policy.value("dead_run_out")
    dead_back = 0 if last.destination_is_depot else policy.value("dead_run_back")
    start = first.start - timedelta(minutes=policy.value("vehicle_check") + dead_out)
    end = last.end + timedelta(minutes=dead_back)

    driving = dead_out + dead_back
    long_route = 0
    run = dead_out
    longest = run
    run_start = first.start - timedelta(minutes=dead_out)
    longest_start = run_start
    pending_piece = False
    gaps: list[Gap] = []
    urban = any(t.urban for t in trips)
    urban_break = False
    full = policy.value("break_full")
    first_piece = policy.value("break_split_first")
    second_piece = policy.value("break_split_second")
    urban_min = policy.value("urban_break")

    def rest(minutes: int, resume: datetime) -> None:
        nonlocal run, run_start, pending_piece, urban_break
        if minutes >= full or (pending_piece and minutes >= second_piece):
            run = 0
            run_start = resume
            pending_piece = False
        elif minutes >= first_piece:
            pending_piece = True
        if urban and minutes >= urban_min:
            urban_break = True

    for index, trip in enumerate(trips):
        stop = min(trip.en_route_break_minutes, _minutes(trip.end - trip.start))
        length = _minutes(trip.end - trip.start) - stop
        driving += length
        if trip.long_route:
            long_route += length
        halves = (length // 2, length - length // 2) if stop else (length,)
        for half, piece in enumerate(halves):
            if half:
                stop_start = trip.start + timedelta(minutes=halves[0])
                stop_end = stop_start + timedelta(minutes=stop)
                kind = "work" if _classify(stop, policy) == "work" else "break"
                gaps.append(Gap(stop_start, stop_end, kind))
                if kind != "work":
                    rest(stop, stop_end)
            run += piece
            if run > longest:
                longest, longest_start = run, run_start
        if index + 1 == len(trips):
            break
        nxt = trips[index + 1]
        gap = _minutes(nxt.start - trip.end)
        if trip.destination == nxt.origin:
            transfer: int | None = 0
        else:
            transfer = transfer_minutes(trip.destination, nxt.origin)
        if transfer is None:
            driving += gap
            run += gap
            if run > longest:
                longest, longest_start = run, run_start
            gaps.append(Gap(trip.end, nxt.start, "work"))
            continue
        transfer = min(transfer, gap)
        driving += transfer
        run += transfer
        if run > longest:
            longest, longest_start = run, run_start
        remaining = gap - transfer
        kind = _classify(remaining, policy)
        if remaining > 0:
            gaps.append(Gap(trip.end + timedelta(minutes=transfer), nxt.start, kind))
        if kind != "work":
            rest(remaining, nxt.start)

    run += dead_back
    if run > longest:
        longest, longest_start = run, run_start

    interruption_gaps = [g for g in gaps if g.kind == "interruption"]
    interruption_minutes = sum(_minutes(g.end - g.start) for g in interruption_gaps)
    work = _minutes(end - start) - interruption_minutes

    return DutyFacts(
        start=start,
        end=end,
        work_minutes=work,
        driving_minutes=driving,
        long_route_driving_minutes=long_route,
        overtime_minutes=max(0, work - policy.value("daily_work_normal")),
        gaps=tuple(gaps),
        longest_driving_without_break=longest,
        urban=urban,
        urban_break_taken=urban_break,
        interruptions=len(interruption_gaps),
        interruption_minutes=interruption_minutes,
        ends_away_from_base=last.destination != profile.home_station,
        longest_run_start=longest_start,
    )
