# Foundation and guided workflow review

Review scope: the uncommitted working tree on `feat/v2-ktel-platform`, including new untracked implementation files. Approved design/plan: `docs/superpowers/{specs/2026-10-30-tenant-onboarding-imports-design.md,plans/2026-10-30-saas-foundation-imports.md}`. One independent fresh-context read-only review was performed; no reviewer subdelegation, commits or pushes.

The review checked legacy migration preflight, tenant context across transactions/pools, narrow identity discovery/revocation/capabilities, conservative spreadsheet matching, and immutable dated/published/reviewed inputs. It reported no Critical findings and two Important findings:

1. Historical source references could collide with newly allocated/manual canonical references; related imports preferred aliases over conflicting canonical records. Fixed by reserving aliases during manual creation/update/allocation and collecting every candidate before relation resolution. Real PostgreSQL regressions cover archived drivers, explicit edits, vehicle registrations, timetable links and inherited collisions.
2. Login/reset lowercased addresses while the legacy database lookup was exact, excluding mixed-case legacy accounts. Migration0009 preserves original spelling, uses case-insensitive discovery and a matching unique index, and refuses pre-existing case collisions with actionable user IDs. Real upgrade/login/reset/duplicate-case regressions cover this behavior.

The review fixes initially added a per-row import lookup. The existing bulk-import query-count regression caught14 reads instead of the allowed2. Reservations now reuse the tenant-locked catalog, cache only within its exact transaction and tenant, and invalidate after alias writes. Tests verify new transactions refresh aliases, tenant switching remains prohibited and another tenant never inherits reservations.

Declined-to-judge items were evaluated against approved scope: full-horizon legality/availability, incidents, driver portal and reports remain later phases; external SMTP/deployment, production restore/rollback, IP/legal approval and capacity acceptance need separate evidence. Complete accessibility needs assistive-technology checks beyond the browser captures. Partial-coverage publication remains subject to existing tenant policy; actual coverage and verifier findings are displayed without inventing a policy.

Acceptance command results and the remaining wider SaaS gates are recorded in `docs/IMPLEMENTATION_STATUS.md` and the plan progress ledger. The review is not a production certification.
