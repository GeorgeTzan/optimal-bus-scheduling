# Scheduling recovery implementation plan

Goal: complete the handover's persisted scheduling and asynchronous CV slice on the existing branch. No commits or pushes.
Architecture: retain FastAPI/PostgreSQL/Next.js and existing revision, verifier, job and outbox boundaries. REST is authoritative. Persist the imported reference problem alongside its revision so subsequent edits never reload mutable fixture data. Use the existing admin flag for write permissions until roles are implemented.
Spec: docs/v2/KTEL_Architecture_Specification_v2.md and handover tasks 1–4.

- [x] 1. Test scheduling REST lifecycle: initialize explicitly from reference dataset, active revision reload, version conflict, locks, publication gate, tenant hiding and permissions. Implement tenant-scoped endpoints and authoritative verification. Store imported problem in a dedicated snapshot table with an explicit SQL migration.
- [x] 2. Test and connect inspector edits, locks, approvals and publication to REST. Stabilize authenticated fetch identity; remove local publication fallback and unfounded compliance claims. Derive timeline/KPIs from persisted responses; display server violations and failures.
- [x] 3. Test and implement an independently running CV queue consumer using persisted snapshots and isolated bounded processes; persist actual progress/candidates and transactional outbox events. Connect authenticated fetch SSE with REST reconciliation and reconnect; no automatic replacement of locked drafts.
- [x] 4. Run complete pytest, frontend typecheck/build and browser integration. Capture real screenshots; compare reference hierarchy and density. Record evidence and remaining risks in implementation status.

Review focus: stale simultaneous writers; cross-tenant references; approval invalidated by edits; published immutability; delayed solver results overwriting manual edits; disconnect/reconnect and job filtering; worker timeout and fencing.

Rulings: existing branch and dirty tree retained per handover. User's explicit no-commit rule overrides plan commit steps. No new design approval needed for explicitly assigned interfaces. No regulatory compliance or production-readiness claim.

Verification ledger: baseline 77 backend tests; final 88 passed in 40.60s. Typecheck and production build passed (existing lint warnings). Five browser workflows passed against production build in 24.9s. Live PostgreSQL stale-writer probe returned 200/409. Independent review findings fixed with candidate-retention and session-response RED→GREEN regressions. Screenshots saved under docs/screenshots/2026-10-30/. All changes remain uncommitted.
