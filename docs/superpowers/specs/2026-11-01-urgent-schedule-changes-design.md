# Guided last-minute schedule changes

Status: approved by the user for implementation. This extends the existing guided dispatcher workflow, whose acceptance and final verification are still in progress.

## Purpose

Help dispatchers respond when a driver cannot work, a trip is cancelled, or an individual assignment needs to change. The user wants an easy, visually clear workflow and liked the drag feedback in the clickable proposal. The interface must communicate what changes, what needs attention, and which schedule is actually published.

## Approaches considered

1. **Guided change with a short review and publication path — selected direction.** Prepare changes against the current schedule, check them, review the impact, then publish through the existing permissions and approval rules. Previous publications remain available. This is the recommended balance of speed and clarity.
2. Change the published schedule immediately: fewer steps, but colleagues may be looking at a different version and history becomes harder to follow.
3. Add an extra formal approval step to every emergency: greater oversight, but potentially slow. The current authorization and approval rules remain authoritative; a new configurable policy is outside this proposal.

## Interaction

- Dragging a trip vertically changes its assigned crew/vehicle row, keeping its scheduled departure and arrival fixed. Horizontal motion never changes the timetable. Moving a trip and changing its public time are separately labelled actions.
- As a trip is dragged, retain a faint original, highlight the target row, show a destination preview at the original time and name both driver and vehicle. Provide text/icon states for checking, ready to review and conflict. Dropping opens a review; it does not automatically publish. Provide the same actions through an accessible **Move to…** control, usable by keyboard and touch.
- A trip action can leave a trip unassigned or propose cancellation. These are distinct states: an unassigned trip still needs coverage; a cancelled service remains visible with a required reason and is excluded from active assignments in the proposed version. Cancellation must never silently erase published history.
- A driver-unavailable action shows affected remaining trips and offers a replacement for selected trips or all remaining trips. Explicitly distinguish replacing just the driver while keeping a bus from moving trips to an existing driver/vehicle pairing; show every affected driver and vehicle before confirmation. No automatic availability or legal eligibility claims.
- For a published day, create a proposed successor based on the selected publication. Show the previous publication as current until an authorized update is published; display old/new assignments, cancellations, reasons, check findings and any uncovered work. A change is not a notification: show only real notification status if a real integration exists.
- In-progress/completed work and frozen history need explicit protection. Never infer a trip actually departed solely from its scheduled time. The design must use recorded operational facts and a conservative reviewed cutoff where facts are missing; it must not silently rewrite already-operated history.
- A separate explicit time-change workflow can be designed later; this delivery must not implement time shifting through drag or imply it is available.

## Validation, safety and permissions

The backend is authoritative. A preview must evaluate actual immutable snapshot inputs, resource eligibility, overlap, transfers and existing independent verifier findings; show precise findings without claiming complete legal compliance. Show checking and failure states and block actions requiring successful validation when checks are unavailable. Version and tenant scope every preview and mutation. Before applying/publishing, recheck the base publication, selected revision and source versions; concurrent edits return a recoverable conflict and retain the user's selections and reason.

Published revisions and assignment history are immutable. A successor must copy the authoritative publication and persist its changes transactionally with reasons, actor, version and audit history. Existing approval, publish and role capabilities remain enforced on the server. New cancellation semantics must flow through snapshots, verification, solver inputs, coverage, historical views and Operations; they cannot be simulated by deleting or merely unassigning a trip. The existing manual patch endpoint and paired-resource model do not by themselves provide driver-only replacement, cancellation or a published-successor workflow; these require deliberate domain work and tests.

Protect against changes to started/completed work, stale source data, a newer publication while editing, no available replacement, locked assignments, partial failures and two dispatchers making concurrent changes. Never fabricate GPS locations, availability, notifications or completed legal verification. Preserve tenant isolation, CSRF, idempotent retries and durable audit history. No automated recovery, passenger messaging, or new approval policy is assumed.

The current verifier groups assignments by paired resource. Driver-only replacement must also verify overlaps by the underlying driver and vehicle across distinct pair IDs; add independent regression coverage before relying on it.

## Operational reports across publications

The current Operations board reads reports attached to its selected publication. When a successor is published, unresolved reports and explicitly recorded departures/completions on the earlier version would therefore disappear from the default latest view. The user delegated this decision; show relevant linked prior-publication reports and recorded facts in the new view with their original version, author and time, without copying or silently reassigning those records. Show the original publication, actor and time, and preserve the original record.

## Builder decisions and sequencing

The implementation plan must first finish the already-approved Operations verification and page-by-page audit. Then design a small backend-supported slice with migrations if necessary and explicit API contracts for previews, cancellation and immutable successor revisions. Choose a suitable accessible drag mechanism compatible with the current frontend; avoid a new dependency unless justified. Specify conservative handling and operator guidance for uncertain operational status, and test daylight saving and tenant isolation. Do not claim unsupported crew availability or regulatory checks.

## Acceptance

Using real persisted schedules, exercise a single trip move, keyboard alternative, a multi-trip driver change, no suitable replacement, cancellation versus unassignment, conflict and stale-version recovery, and review/publication of a successor while preserving prior history. Check unauthorized/read-only users, two organizations, concurrent dispatchers and already-operated work. Verify the drag preview at desktop and mobile/touch sizes and provide a usable non-drag route. Run backend and frontend suites, actual rendered browser tests and screenshots. All changes remain uncommitted and unpushed until the user instructs otherwise.
