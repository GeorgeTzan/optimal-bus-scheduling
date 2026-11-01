# Office availability, leave and maintenance

How office staff state who can work and which vehicles are usable, and how that reaches the solver, the verifier and publication. Design: `docs/superpowers/specs/2026-11-01-office-availability-maintenance-design.md`. Requirements: OFFICE, FLEET, SEC in `docs/PRODUCT_SCOPE_AND_SAFETY_REVIEW.md`.

## What the software records

| Record | Meaning | Ends when |
|---|---|---|
| Weekly working pattern | A driver works these weekdays and hours within a validity range of at most 366 days. | The range ends or it is retired. |
| Dated period (`available`) | Working time for one date. It replaces the weekly pattern for that local date. | Its end. |
| Dated period (`unavailable`) | An absence. The end may be unknown (open). | Its end, or it is retired. |
| Leave request | pending, approved, rejected or cancelled. Approval creates exactly one linked absence. | Cancelling the request retires only its linked absence. |
| Planned maintenance | A finite vehicle reservation. | Its end, or it is cancelled. |
| Out-of-service hold | A vehicle is unusable. It has no end until someone releases it. An estimated return never ends it. | An explicit release with actor, time and note. |

Missing working time is **unknown**, never "available". A new draft cannot be created while a paired driver has no recorded working time. Service day names the drivers and links to the Office section.

## Who may do what

Nothing is granted by default, not even to administrators. An administrator (`members.manage`) grants these per member in **Office → Access**:

| Grant | Allows |
|---|---|
| `availability.manage` | Record working time, absences and leave requests; retire periods; cancel pending leave; record an external contact's leave decision. |
| `maintenance.manage` | Record and edit planned maintenance and holds (not a hold's start). |
| `maintenance.release` | Release a hold, cancel a hold entered in error, move a hold's start. |
| `office.notes.read` | See leave category and private notes. |

Leave authority comes **only** from approval routes (Office → Access): an organization default, or a route for one driver, naming an organization member or an external contact (for example a bus owner). A route member decides without any grant. Staff with `availability.manage` can record an external contact's decision; the record keeps both the recorder and the stated decision-maker and is never shown as the contact's own approval. A member whose account is linked to the driver can never decide, edit or retire that driver's leave or absence.

## How it reaches scheduling

1. `availability_for_resources` computes usable windows: working time minus absences minus vehicle blockers. Intervals are half-open UTC.
2. A new draft freezes the windows (`ktel-operational-v2`) with a fingerprint and per-resource provenance.
3. The bounded CV solver never assigns a trip, or the travel to it, outside a window. The original reference solver stays unmodified and refuses availability problems.
4. The independent verifier recomputes from the frozen windows: `RULE_AVAILABILITY_TRIP`, `RULE_AVAILABILITY_TRANSITION`, `RULE_AVAILABILITY_UNKNOWN`. It never trusts a solver flag.
5. An unpublished draft whose availability changed is refused at patch, request-approval, approve and publish with `availability_changed` (409). Its `source_review_required` flag is true.
6. A published schedule is never changed by an absence. **Office → Affected trips** (`GET /api/v1/office/impacts`) lists affected trips, derived and read-only. Repair uses the existing reviewed successor workflow.

Repair details: a successor re-computes availability for every crew, including replacement crews, from current records. Trips with a recorded departure or completion are exempt; the exemption is derived on the server and cannot be supplied. A locked trip can be released inside the same change (`unlock: true` on its patch) only if it has an availability conflict; the change reason and the release are audited.

## Operating notes

- Migrations `0013`–`0016`; the availability migrations stop with a row count if the old availability tables hold data. After upgrading run `uv run python -m db.provision_runtime --refresh-grants`. The office audit table is insert-only for the API role; the worker role has no access to office tables.
- Bounds: 100 items per batch, 366-day pattern validity, 62-day lists, 31-day impact range. These are input limits, not capacity claims.
- Not claimed: legal driving-hour or rest compliance, medical fitness, vehicle roadworthiness, notification delivery, or that an approval came from an authenticated external person.
- Known limit: on phones the office tables scroll sideways with the action column pinned; a card layout is not built.
