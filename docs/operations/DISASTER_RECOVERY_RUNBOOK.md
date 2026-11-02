# KTEL Operations SaaS — Disaster Recovery & Operational Runbook

**Audience:** Site Reliability Engineers, DevOps, System Administrators, Lead Dispatchers  
**Classification:** Operational Procedure  
**Last Revised:** 2026-10-30

---

## 1. Overview & Architecture Summary

The KTEL Operations SaaS platform utilizes:
- **FastAPI Modular Monolith:** Authoritative REST API and authenticated Server-Sent Events (SSE).
- **PostgreSQL 16:** Authoritative multi-tenant operational data store with Row-Level Security (RLS) and Transactional Outbox.
- **Python Optimization Workers:** Dedicated background processes executing Christos Valouxis's CV Solver v1 under isolated supervisor wrappers with enforceable timeouts (`SIGTERM` -> `SIGKILL`).
- **Next.js 15 Bilingual Frontend:** Light/Dark accessible interface with Greek default and virtualized timeline.

---

## 2. Automated PostgreSQL Backup & Restore Drills

### 2.1 Daily Automated Backup
PostgreSQL dumps are executed via cron into an encrypted storage target:

```bash
# 1. Automated Snapshot Script (runs daily at 02:00 Athens local time)
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/var/backups/ktel_postgres"
mkdir -p "$BACKUP_DIR"

docker exec -t optimal-scheduling-system-db-1 pg_dump \
  -U user \
  -d scheduling_db \
  -F c \
  -b -v \
  -f "/tmp/db_backup_${TIMESTAMP}.dump"

docker cp optimal-scheduling-system-db-1:"/tmp/db_backup_${TIMESTAMP}.dump" "${BACKUP_DIR}/"
gzip -9 "${BACKUP_DIR}/db_backup_${TIMESTAMP}.dump"
```

### 2.2 Restoration Drill into an Isolated Staging Environment
To verify backup integrity without affecting production:

```bash
# 1. Create clean disposable verification database
createdb -h 127.0.0.1 -U user -T template0 scheduling_verify_restore

# 2. Restore custom-format dump
pg_restore -h 127.0.0.1 -U user -d scheduling_verify_restore -v "${BACKUP_DIR}/db_backup_${TIMESTAMP}.dump"

# 3. Execute tenant isolation and schema compliance tests
DATABASE_URL="postgresql://user:password@127.0.0.1:5432/scheduling_verify_restore" \
  pytest tests/security/test_pilot_security.py tests/security/test_tenant_rls.py -v
```

---

## 3. Worker Crash & Lease Fencing Recovery

### 3.1 Failure Scenario: Optimization Worker Node Crashes Mid-Run
When an optimization worker host loses power or suffers a hard kernel panic:

1. **Lease Expiration:**
   - The job has a database lease in `domain_jobs` with `lease_expires_at = now + 60s`.
   - Without active heartbeats from the crashed worker, the lease expires within 60 seconds.
2. **Automatic Re-Claim by Healthy Worker:**
   - Next available worker queries `SELECT ... FOR UPDATE SKIP LOCKED` where `lease_expires_at < NOW()`.
   - The monotonic `attempt_token` is incremented (e.g. from 1 to 2).
3. **Fencing Protection:**
   - If the crashed worker revives unexpectedly, its attempts to call `heartbeat()` or `complete_job()` using stale token 1 are strictly rejected.
   - Zero corrupted or duplicate results can be committed.

### 3.2 Manual Force-Kill for Runaway Jobs
If an optimization run needs immediate administrative termination:

```bash
# 1. Send administrative cancel command via API
curl -X POST "https://api.ktel-scheduling.gr/optimization/runs/{RUN_ID}/cancel" \
  -H "Authorization: Bearer ${SUPERVISOR_JWT}"

# 2. If subprocess fails to terminate, the supervisor wrapper automatically dispatches SIGKILL after 1.0s grace period.
```

---

## 4. Disruption & Disconnected Driver Procedure

### 4.1 Bus Breakdown / Driver Illness Protocol
1. **Report Incident:** Dispatcher or driver submits incident via UI modal or API:
   `POST /incidents` (`VEHICLE_BREAKDOWN` or `DRIVER_SICK_LEAVE`).
2. **Frozen-Prefix Recovery:**
   - Past and currently operated trips prior to `as_of_minutes` remain permanently frozen (`split_operated_future`).
   - Disrupted future trips are reassigned to available reserve pairings.
3. **Human Dispatcher Approval Gate:**
   - The system generates a `RecoveryProposal`.
   - **Crucial Rule:** The platform NEVER auto-publishes without human dispatcher signoff (`approve_recovery`).
4. **Driver Portal Notification:**
   - Once approved, assigned drivers receive updated shift details via the Driver Portal.

---

## 5. Software Release Rollback Plan

If a newly deployed version exhibits unforeseen issues:

1. **Container Rollback:**
   ```bash
   docker-compose -f docker-compose.yml down
   docker-compose -f docker-compose.rollback.yml up -d
   ```
2. **Database Migrations:**
   All Alembic migrations include strictly verified `downgrade()` steps.
   ```bash
   alembic downgrade -1
   ```
3. **Audit Inspection:**
   Inspect `domain_scheduling_audit_logs` to ensure all publications and revisions maintain unbroken provenance.
