# KTEL SaaS — UI/UX Design System Specification

## 1. Mockup Analysis & Architectural Synthesis

The visual foundation of the KTEL Operations SaaS is synthesized from four high-fidelity production mockups located at `docs/v2/KTEL_UI_Mockups/ktel_ui_mockups/`:

### Mockup 1: Light Scheduling Dashboard (`01_light_scheduling_dashboard.png`)
* **Core Strengths**: 
  - Crisp, modern high-contrast light theme with soft slate backgrounds (`#f8fafc`) and pure white cards (`#ffffff`).
  - Top-tier KPI summary card row with circular progress rings (Scheduled Trips, Buses in Service, Active Drivers) and delta badges (+3% On-Time Departures).
  - Dedicated right-side contextual drawer (`Trip Details`) with station sequence breadcrumbs, terminal platform numbers, bus/driver metadata badges, and trip action buttons (`Edit Trip`, `Duplicate`, `More Actions`).
  - Bottom tabular view with filter tabs (`Trips (142)`, `Conflicts (3)`, `Unassigned (4)`, `Driver Availability`).
* **Adopted Elements**: The right-side slide-over inspector, the KPI card progress ring design, and the tabular conflict/unassigned bottom drawer.

### Mockup 2: Dense Scheduling Studio (`02_dense_scheduling_studio.png`)
* **Core Strengths**:
  - High information density tailored for veteran Greek KTEL dispatchers managing hundreds of daily departures.
  - Multi-tiered filter toolbar: Region, Line/Route, Vehicle Type, Depot, Status dropdowns alongside Day/Week/Month view toggles.
  - Quick action toolbar directly above the Gantt chart: `Auto-assign`, `Optimize`, and state toggles (`All`, `Assigned`, `Unassigned`).
  - Candidate Schedules bottom drawer comparing multiple solver outputs (`Balanced Plan`, `Cost Optimized`, `Current Manual`) with real cost deltas (-15%, -6%), vehicle utilization, driver utilization, and a prominent `Apply Schedule` action.
  - Legal & Compliance card in the inspector verifying EU Regulation (EC) 561/2006 (working hours, rest periods, tachograph limits).
* **Adopted Elements**: Multi-tiered filter bar, optimization candidate comparison cards, and EC 561/2006 compliance checklist.

### Mockup 3: Greek Weekly Planner (`03_greek_weekly_planner.png`)
* **Core Strengths**:
  - Native bilingual localization: fully localized Greek typography, day headers (`Δευ 14/4`, `Τρί 15/4` ... `Κυρ 20/4`), and Greek operational terminology.
  - Collapsible resource groups: `Οδηγοί (Drivers)` with avatar badges, cumulative weekly driving hours tracking (`37h / 40h`), and overtime alert indicators (`41h / 40h !`); `Οχήματα (Vehicles)` with maintenance status badges (`Εντός`, `Συντήρηση`).
  - Conflict visualization: trip cards highlighted with bold red borders and warning icons for overlapping or illegal assignments.
  - Optimization scenario cards with direct solver cost and vehicle efficiency projections.
* **Adopted Elements**: Native Greek typography and time formats, driver weekly driving hour badges (`Xh / 40h`), collapsible resource grouping, and high-visibility conflict warning styling.

### Mockup 4: Dark Operations Control Center (`04_dark_operations_control_center.png`)
* **Core Strengths**:
  - Premium deep-navy dark mode (`#0b1329` / `#0f172a`) optimized for multi-monitor operations control rooms and night shifts.
  - Live operations pulse with real-time status pills (`Live Operations`, `On time`, `Delayed`, `Disrupted`, `Completed`).
  - Interactive Greek intercity network topology map linking primary regional KTEL hubs (Athens, Thessaloniki, Patras, Larissa, Volos, Ioannina, Heraklion, Kalamata).
  - Disruption triage & recovery panel: Live Alerts feed paired with Recommended Recovery Actions with one-click `Approve` / `Reject` dispatch controls.
* **Adopted Elements**: Dark operations theme variables, live incident alert cards, and dispatcher approval-gated recovery action cards.

---

## 2. Design Tokens & Theme Specification

### Color Tokens
```css
:root {
  /* Surface colors */
  --bg-primary: #f8fafc;
  --bg-surface: #ffffff;
  --bg-sidebar: #0f172a;
  --bg-sidebar-active: #1e293b;
  --border-subtle: #e2e8f0;
  --border-strong: #cbd5e1;

  /* Typography */
  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-muted: #94a3b8;
  --text-inverse: #ffffff;

  /* KTEL Brand Accents */
  --brand-primary: #0284c7;        /* Aegean Blue */
  --brand-primary-hover: #0369a1;
  --brand-accent: #0d9488;         /* Teal / Sea Green */
  --brand-accent-hover: #0f766e;

  /* Status & Compliance */
  --status-scheduled-bg: #ecfdf5;
  --status-scheduled-text: #059669;
  --status-scheduled-border: #a7f3d0;

  --status-progress-bg: #eff6ff;
  --status-progress-text: #2563eb;
  --status-progress-border: #bfdbfe;

  --status-delayed-bg: #fffbeb;
  --status-delayed-text: #d97706;
  --status-delayed-border: #fde68a;

  --status-conflict-bg: #fef2f2;
  --status-conflict-text: #dc2626;
  --status-conflict-border: #fecaca;

  --status-maintenance-bg: #f1f5f9;
  --status-maintenance-text: #64748b;
  --status-maintenance-border: #e2e8f0;
}

[data-theme="dark"] {
  --bg-primary: #0b1329;
  --bg-surface: #111e38;
  --bg-sidebar: #070d1e;
  --bg-sidebar-active: #1a2744;
  --border-subtle: #1e293b;
  --border-strong: #334155;

  --text-primary: #f8fafc;
  --text-secondary: #cbd5e1;
  --text-muted: #64748b;
  --text-inverse: #0f172a;

  --brand-primary: #38bdf8;
  --brand-primary-hover: #0284c7;
  --brand-accent: #14b8a6;
  --brand-accent-hover: #0d9488;

  --status-scheduled-bg: #064e3b;
  --status-scheduled-text: #6ee7b7;
  --status-scheduled-border: #047857;

  --status-conflict-bg: #450a0a;
  --status-conflict-text: #fca5a5;
  --status-conflict-border: #991b1b;
}
```

---

## 3. Component Architecture & Interaction Standards

1. **Top Navigation Bar (`Navbar.tsx`)**:
   - Organization tenant switcher (e.g. `KTEL Thessalonikis`, `KTEL Korinthias`).
   - Global keyboard search (`⌘K` / `Ctrl+K`) for trips, drivers, buses, and routes.
   - Day / Night theme toggle switch.
   - Live notification dropdown with unread badge count.
   - User profile dropdown with role badge (e.g., `Operations Manager`, `Dispatcher`, `Driver`).

2. **Scheduling Timeline Studio (`SchedulingStudio.tsx`)**:
   - Header control ribbon: Date navigation (`< Today >`), View mode (`Day`, `Week`, `Month`), Resource view (`Buses`, `Drivers`), Multi-attribute filters.
   - Action triggers: `Optimize` (triggers background solver worker), `Publish Schedule`, `Auto-assign`.
   - Virtualized Gantt canvas with interactive trip blocks, current time vertical guide (`Now`), layover hatch patterns, and conflict badges.
   - Bottom candidate comparison tray: displays real solver candidates (`Balanced`, `Cost-optimized`, `Current`) with metrics comparison and one-click preview/apply.

3. **Trip & Assignment Inspector (`AssignmentInspector.tsx`)**:
   - Contextual slide-out drawer on the right.
   - Displays trip stops, departure/arrival platform, assigned bus, driver license status.
   - Full EU 561/2006 legal compliance checklist (driving limit, daily rest, weekly hours).
   - Direct action buttons: Lock assignment (`is_locked`), Reassign, Duplicate, Remove.

4. **Operations Control Center (`OperationsCenter.tsx`)**:
   - Network overview cards with live sparklines and delay tracking.
   - Active disruptions table with severity tags (`High`, `Medium`, `Low`).
   - Disruption recovery queue with human-in-the-loop `Approve` / `Reject` actions.

---

## 4. Internationalization & Regional Rules

- **Default Locale**: Greek (`el-GR`) with seamless runtime toggle to English (`en-US`).
- **Date Formatting**: `Intl.DateTimeFormat("el-GR", { weekday: "short", day: "numeric", month: "short", year: "numeric" })`.
- **Currency**: `Intl.NumberFormat("el-GR", { style: "currency", currency: "EUR" })`.
- **Time Zone**: `Europe/Athens` with robust handling of daylight saving adjustments.
