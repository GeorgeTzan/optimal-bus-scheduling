# Driver work rules

How the software checks driver working time, who can change the limits, and what it cannot yet do. Solver authors: `docs/operations/WRITING_A_SOLVER.md`.

## Legal basis — «Προς επιβεβαίωση» (to be confirmed by counsel)

The table is a versioned constant, `LEGAL_RULES_VERSION = "gr-pd54-1998+eu561-2026-11"` (`backend/app/domain/workrules/legal.py`), shown with its sources in **Settings → Work rules**. It has not been confirmed by a lawyer. The software does not certify legal compliance.

Greek PD 54/1998 applies to all KTEL drivers. EU Regulation 561/2006 applies in addition to regular passenger services on routes over 50 km (Art. 3(a)). The software enforces the stricter value of all applicable rules. A route with unknown length is treated as over 50 km.

| Rule | Source | Value | Kind |
|---|---|---|---|
| Daily work, normal (overtime above) | PD 54/1998 Art. 3(1) | 480' (8 h) | fixed |
| Daily work, maximum | PD 54/1998 Art. 3(2), 6(3) | 600' (10 h) | max |
| Daily work, emergency | PD 54/1998 Art. 6(4)-(5) | 660' (11 h) | max |
| Overtime per year | PD 54/1998 Art. 6(3) | 7 200' (120 h) | max |
| Overtime per year, absolute (with emergency) | PD 54/1998 Art. 6(3), 6(5) | 10 800' (180 h) | max |
| Weekly work, normal | PD 54/1998 Art. 3 | 2 400' (40 h) | fixed |
| Weekly work, maximum | PD 54/1998 Art. 3 | 2 700' (45 h) | max |
| Continuous driving before a break | PD 54/1998 Art. 4(2); EU 561/2006 Art. 7 | 270' | max |
| Break, whole | PD 54/1998 Art. 4(2)-(3); EU 561/2006 Art. 7 | 45' | min |
| Break, split | PD 54/1998 Art. 4(2)-(3); EU 561/2006 Art. 7 | 15' then 30' | min |
| Urban route break | PD 54/1998 Art. 4(4) | 30' | min |
| Daily driving, routes over 50 km | EU 561/2006 Art. 6 | 540' (9 h) | max |
| Daily driving, extended | EU 561/2006 Art. 6 | 600' (10 h), at most twice per week | max |
| Weekly driving, routes over 50 km | EU 561/2006 Art. 6 | 3 360' (56 h) | max |
| Fortnight driving, routes over 50 km | EU 561/2006 Art. 6 | 5 400' (90 h) | max |
| Daily rest | PD 54/1998 Art. 5(2) | 720' (12 h) | min |
| Daily rest, reduced | PD 54/1998 Art. 5(2) | 600' (10 h), once per week, compensated | min |
| Weekly rest | PD 54/1998 Art. 2(ε), 5(2) | 2 880' (48 h) after at most 5 working days | min |
| Sunday rest | PD 54/1998 Art. 2(ε), 5(2) | at least every 4 weeks | max interval |
| Interruptions over 60' | PD 54/1998 Art. 2(η), 5(1) | at most 3 and 540' (9 h) per week | max |
| Vehicle check | PD 54/1998 Art. 3(3)-(4) | 10', counted as work | fixed |
| Dead run | PD 54/1998 Art. 3(3)-(4) | 15' out, 10' back, counted as work | fixed |

Directive 2002/15/EC weekly limits are looser than PD 54/1998 and are not binding here.

Kinds: `fixed` cannot be changed. `max` limits may only be lowered, `min` limits only raised.

Legal findings block: a draft with a legal finding cannot be sent for approval or published.

## Company limits (stricter only)

Settings → Work rules (`organization.manage`) lets a company set its own value per rule. A value is accepted only if it is at least as strict as the legal one: a `max` limit not above the legal value, a `min` limit not below it. A looser value is rejected with the legal value shown. «Reset to legal» removes the company value. Each save is versioned and audited; the report of every verification records `legal_rules_version` and the company version.

New limits and new legal versions apply to drafts from then on. Already published days are flagged in the Studio tab, not re-blocked.

## Warning rules (default off, opt-in)

Three company rules are off by default and are switched on per company in the same screen:

| Rule | Meaning |
|---|---|
| `overnight_rest_day` | A rest day follows an overnight away from base. |
| `no_consecutive_overnight` | No two consecutive overnights. |
| `shift_rotation` | After an afternoon or night week, the next week starts with mornings if possible (PD 54/1998 Art. 8). |

Findings from these rules are warnings. They never block, and they can be overridden.

Per driver (Drivers → record → Preferences and restrictions, `drivers.write`): overnight allowed, split shift allowed, must return to base, preferred and forbidden routes. Per vehicle (`fleet.write`): forbidden routes. Per route (`timetable.write`): `service_type`, `intercity` (default) or `urban`, set by the office, never derived from distance. Violations of these restrictions are warnings.

## Baseline on adoption

History before the software was used is unknown, and several rules need history. Each driver may have opening balances, valid as of a stated date:

| Field | Import column |
|---|---|
| As of date | `baseline_as_of` |
| Overtime used this calendar year | `baseline_overtime_hours` |
| End of the last duty | `baseline_last_duty_end` |
| End of the last weekly rest | `baseline_last_weekly_rest_end` |
| Last weekly rest was at the home base | `baseline_last_weekly_rest_at_base` |
| Reduced-rest compensation still owed | `baseline_owed_rest_hours` |

Entered on the driver's tab (`drivers.write`) or through the driver import columns above (plus `overnight_allowed`, `split_shift_allowed`, `must_return_to_base`). Route and vehicle rules have their own import sheet; route rules need the route to be saved in an earlier upload. Every change is audited. The `as_of` date must be before today (tenant timezone), and the two instants must carry a timezone. A baseline is locked once the driver has a published day on or after its `as_of` date: the stored baseline cannot be changed at all (no field, no new date), and a new one cannot be dated on or before a published day. The baseline describes the state at the end of `as_of`, so a published `as_of` day would be counted twice. The timeline treats it as known history. A driver without one gets a `WR_HISTORY_UNKNOWN` warning naming the days, and rules that need that history are evaluated on known data only.

Dates and times in the Studio and in imports follow the tenant timezone (`Europe/Athens` by default). Stored instants are UTC. Day and week boundaries are local: a week is Monday 00:00 to Sunday 24:00.

## Overrides

- Only company-rule findings (warnings) can be overridden. Legal findings cannot.
- Permission `schedule.approve`; a reason is required; actor, time and reason are stored with the revision.
- An override carries to a child revision only when the finding is identical (same rule, driver, trips and measured value). Otherwise it must be given again.

## Emergency (urgent changes only)

- Allows a daily work limit of 660' instead of 600'.
- Only through the urgent-change flow, by a user with `schedule.publish`, with a required reason stored on the change record. Manual Studio edits cannot use it.
- Set per driver on the change.
- Emergency work counts only toward the absolute yearly cap of 10 800', not toward the 7 200' overtime cap.

## Definitions

- **Duty.** From the vehicle check before the first trip to the dead run after the last. Dead runs and empty transfers count as work and as driving.
- **Gap inside a duty.** Under 15': work (waiting). 15' to 60': a break piece; it counts as work and can satisfy the break rule. Over 60': an interruption; it is not work time, satisfies the break rule, counts toward the weekly interruption limits and makes the duty a split shift. A gap long enough to be a reduced daily rest (600', or the company's stricter value), measured as a rest would be from the end of the dead run back to the start of the next vehicle check, is not an interruption: it ends one duty and starts another on the same service day. The daily rest rules measure it (12 h, or 10 h once per week with compensation), and each duty has its own vehicle check, dead runs, daily work, daily driving and overtime limits. A service day with two duties is still one working day for the weekly rest count.
- **Split shift.** A duty with at least one interruption. If the driver's `split_shift_allowed` is false, a warning (overridable). Legal interruption limits still block.
- **Overtime.** Daily work above 480'. The weekly cap is a separate check; hours are not counted twice.
- **Window.** Service day minus 28 days to plus 7 days, plus calendar-year overtime totals. A change to a published day is checked against the following week; breaks found on later days are reported against the changed day.
- **Existing violations.** Verification runs with and without the draft. Only findings the draft creates or worsens block it; findings already present show as warnings.
- **Totals already over a limit.** Weekly, fortnight, interruption and yearly overtime totals report a finding on every day that adds to a total already above the limit, and the weekly rest rule on every working day that extends an over-long streak. A draft that adds more to an exceeded total is therefore blocked on its own day; a draft that adds nothing leaves the earlier findings as warnings.

## Known limitations

- The emergency flag is not inherited through later changes. A later non-emergency change to the same day treats emergency duties as normal ones, which can count them toward the 7 200' cap and report the 660' duty as a breach. This fails closed (blocks, never allows).
- The solver's budget check treats a driver's whole service day as one duty, so it may refuse a morning and evening roster with a daily rest between them that the verifier would accept. This fails closed.
- The solver sees per-day budgets (duty length, breaks, forbidden routes, earliest start, home base) but not history-dependent rules such as weekly rest due or reduced-rest compensation owed. The verifier rejects such candidates afterwards.
- Past duties are evaluated with the current route and depot data, not a frozen copy. Later edits to route length, `service_type` or depots can change the result for past days.
- The Scheduling Studio and the driver baseline form use a hard-coded `Europe/Athens` timezone; the backend uses the tenant timezone. Non-Athens tenants may see day boundaries differ in those two screens.
- Overtime of the prior year-to-date (1 January to 29 days before the service day) is computed from past snapshots and cached in each API process, keyed by the tenant's publication, delay, emergency-change, station and route data; any new publication recomputes it. Each process keeps one entry per tenant, so memory stays bounded by the number of tenants. The first request per process after a change pays the full cost (about 3.4 s for 300 published days of 200 trips in the performance test; about 0.4 s when cached).
- Unknown history, such as days without a publication or baseline, is reported as a warning, not as an error.

## Deployment

1. Apply the migrations in order: `0019_driver_work_rules`, then `0020_import_route_rules` (`uv run python -m db.migrations upgrade`).
2. Refresh the runtime role grants so the API role can read and write the new tables: `uv run python -m db.provision_runtime --refresh-grants`. Without this step every work-rule read fails.
3. Optimisation jobs enqueued before the deploy carry no `work_context`. The worker runs them without driver budgets (it does not fail); their candidates are checked against the work rules at every gate (send for approval, approve, publish), so a candidate that breaks a rule is rejected there. Draining the queue first avoids such rejections but is not required.
4. Source and pairing fingerprints change once after the deploy, because routes now carry `service_type` and the old fixed limit fields were dropped from the snapshot. Pairings confirmed before the deploy show as changed and must be confirmed again.
