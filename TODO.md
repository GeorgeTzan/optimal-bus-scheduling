# TODO - Optimal Bus Scheduling System

## Authentication 

Backend auth is already built (`/auth/register`, `/auth/login`, `/auth/me`).

Frontend needs:
- [ ] Auth context provider (store JWT, user state)
- [ ] Login page
- [ ] Register page  
- [ ] Protected route wrapper
- [ ] Logout functionality
- [ ] Token refresh logic

## Multi-Tenant Data Flow (After Auth)

- [ ] File upload endpoint (JSON/DAT files)
- [ ] Parse uploaded files and store in PostgreSQL
- [ ] Associate schedules with user's KTEL
- [ ] Filter all queries by KTEL ID
- [ ] Empty dashboard for new users

---

## 💡 Feature Ideas for Thesis

### Solver Improvements
- [ ] **Multiple algorithms** - Add Genetic Algorithm, Simulated Annealing for comparison
- [ ] **Algorithm benchmarking** - Compare runtime, idle time, buses used across algorithms
- [ ] **Constraint customization** - Let users set max trips per driver, break requirements
- [ ] **What-if analysis** - "What if we had 5 fewer buses?"

### Visualization Enhancements  
- [ ] **Timeline zoom** - Zoom into specific hours
- [ ] **Driver view** - Show schedule from a single driver's perspective
- [ ] **Station view** - Show all trips arriving/departing from a station
- [ ] **Conflict highlighting** - Show overlapping assignments in red
- [ ] **Export to PDF** - Generate printable schedules for drivers

### Analytics & Reporting
- [ ] **Daily/weekly summaries** - Trips completed, total km, idle time trends
- [ ] **Driver workload balance** - Bar chart showing trips per driver
- [ ] **Station heatmap** - Which stations are busiest at what times
- [ ] **Cost estimation** - Estimate fuel/driver costs based on schedule

### Real-World Features (For Production)
- [ ] **Live tracking integration** - Connect to GPS for real-time bus positions
- [ ] **Delay handling** - Re-optimize when a bus is delayed
- [ ] **Driver preferences** - Some drivers prefer certain routes
- [ ] **Break scheduling** - Automatic break insertion per labor laws
- [ ] **Multi-day scheduling** - Weekly schedules, not just single day

### Technical Improvements
- [ ] **Alembic migrations** - Proper database schema versioning for production updates
- [ ] **API rate limiting** - Prevent abuse
- [ ] **Caching** - Cache solver results for identical inputs
- [ ] **Background jobs** - Run solver async for large datasets
- [ ] **Audit log** - Track who changed what schedule

---

## 📝 Thesis Writing Notes

Good points to mention:
- Multi-tenant architecture designed from start (DB schema ready)
- Production monitoring with Sentry
- Containerized deployment with Docker
- Constructive heuristic with deadheading support
- Fairness constraint (balanced driver workload)
- Real KTEL data format support (DAT files)
