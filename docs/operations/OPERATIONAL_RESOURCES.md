# Canonical operational resources

Drivers, vehicles and stations are real organization-owned records, separate from the historical reference archive used by the existing Studio revision. The Drivers and Fleet screens read these registers. They do not derive rosters, names, registrations or capacity from fixed reference driver/bus pairs.

Routes under `/api/v1`:

- `GET/POST /drivers`, `GET/PATCH /drivers/{id}`
- `GET/POST /vehicles`, `GET/PATCH /vehicles/{id}`
- `GET/POST /stations`, `GET/PATCH /stations/{id}`
- `GET /setup/readiness`

Lists accept `q`, `active_only`, `page` and bounded `page_size` (1–100, default 25), returning `items`, `total`, `page`, `page_size`. Unknown record IDs outside the signed-in organization return 404. Payloads cannot supply organization identity or arbitrary properties. Required names/references cannot be cleared in patches. Home station references must belong to the same organization and be active; database composite foreign keys independently enforce ownership.

Writes require role capabilities: drivers.write, fleet.write or timetable.write. Reads require resources.read. PATCH requires the last displayed positive `version`; writes lock and re-read, return 409 on stale versions and increment once on success. Concurrent writers using one version produce exactly one success. Registration conflicts are case-insensitive in PostgreSQL. External-source/key pairs are tenant-unique and both present or both absent; manual forms do not silently attach import identities.

Drivers need a first and last name. Staff references are optional for manual creation; readable D00001-style references are generated under an organization lock. Vehicles need an actual fleet category and either a registration or explicit fleet reference; omitted references are generated. Unknown capacity remains null and renders as “Not recorded”. New code never assumes 50 seats or substitutes one bus type for every vehicle. Stations need a familiar name; the alternate language can be completed later without inventing a translation.

Archiving is a versioned `is_active=false` update, not deletion. Active home-base references, active timetables and linked driver accounts block relevant archive actions with a repair message. Stored scheduling snapshots are not rewritten by register changes. Current and upcoming active daily pairings also block archive actions until the pairing is removed. Canonical Studio draft generation remains a later integration gate.

A new organization sees a checklist based on persisted active records. Each resource save stands alone; reload retains it. Optional form details are collapsed, selectors use names/codes, errors keep entries intact, and native modal dialogs trap keyboard focus and return focus on close. The normal welcome/error flow has no shared-reference import shortcut. The existing reference Studio revision remains available for its established regression scenarios until canonical snapshot integration is completed.

Recurring services and dated preparation (migration 0006)

- `/api/v1/timetables` stores explicit local clocks, arrival-day offsets, weekdays, validity dates and eligible vehicle categories. No arrival rollover, capacity or vehicle category is inferred. PATCH requires the saved version. Route variants preserve existing route inputs instead of mutating shared history.
- Date exceptions under `/timetables/{id}/exceptions` explicitly cancel/add services within validity, replace times or select a repeated DST clock occurrence. All unresolved clock fields are reported together.
- `POST /timetables/materialize` takes service_date and the exact active template version map. It validates the whole date first, then creates immutable dated instances with UTC instants, source versions and input hash. Identical preparation reuses the same instance; corrections create new instances. `GET /timetables/dated-trips` reads current saved instances without creating rows.
- `/pairings` selects actual active drivers, vehicles and starting stations for a date. Confirmation records current source versions and a planning-input fingerprint. Changes to planning inputs require review; cosmetic/contact edits do not. Active driver and vehicle uniqueness is enforced per date. Date copy produces unconfirmed records for explicit review.
- `/transfers` records operator-confirmed directed travel minutes; unknown values block readiness. `POST /transfers/batch` saves the reviewed group atomically. Changes in station planning inputs require transfer review; source snapshots include transfer provenance.
- `/setup/readiness?service_date=YYYY-MM-DD` reports persisted counts and actual date issues, confirmed pairings, missing transfers, prepared trips and immutable source versions. Read endpoints do not materialize trips.

The Timetables screen guides route/times then calendar/category entry. Stations can be created in context. “Change one date” adds an explicit cancellation, extra service within validity or restoration of normal rules; existing exceptions are versioned rather than duplicated. Service day groups pairings, travel-time review and dated preparation into three saved steps. Selecting a date is a tenant/user-scoped browser preference only; saved operational records remain server-authoritative. This slice does not claim full-horizon driving/rest/availability compliance or publish a schedule automatically.
