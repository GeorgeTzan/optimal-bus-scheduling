# Optimal Bus Scheduling

## Screenshots

**Scheduling studio**

![Scheduling studio (light)](docs/screenshots/2026-11-01/studio-desktop-light.png)
![Scheduling studio (dark)](docs/screenshots/2026-11-01/studio-desktop-dark.png)
![Published canonical schedule](docs/screenshots/2026-11-01/studio-canonical-published.png)

**Daily operations**

![Operations](docs/screenshots/2026-11-01/operations-desktop.png)
![Service day prepared](docs/screenshots/2026-10-31/service-day-prepared.png)

**Spreadsheet imports**

![Import review](docs/screenshots/2026-10-31/import-review.png)

**Resources and timetables**

![Vehicle roster](docs/screenshots/2026-10-31/vehicle-roster.png)
![Timetable roster](docs/screenshots/2026-10-31/timetable-roster.png)
![Travel times](docs/screenshots/2026-11-01/travel-times-editable.png)

**Greek UI and mobile**

<p>
  <img src="docs/screenshots/2026-11-01/studio-greek-dark.png" alt="Studio in Greek" width="62%">
  <img src="docs/screenshots/2026-11-01/operations-mobile.png" alt="Operations on mobile" width="30%">
</p>

## Prerequisites

- Docker and Docker Compose installed on your system.

## Installation and Execution

1. Clone the repository:
   ```bash
   git clone https://github.com/GeorgeTzan/optimal-bus-scheduling.git
   cd optimal-bus-scheduling
   ```

2. Create environment files:
   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```

3. Start the application using Docker Compose:
   ```bash
   docker-compose up --build
   ```

4. Open your browser and navigate to:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000

## Usage

1. Click "Run Solver" to generate the optimal bus schedule
2. View the Gantt chart visualization of bus assignments
3. Click on any trip bar to see trip details
4. Switch between Buses, Trips, and Drivers tabs

## Technologies Used

- Frontend: Next.js, TypeScript, Tailwind CSS, React
- Backend: FastAPI, Python
- Database: PostgreSQL
- Containerization: Docker, Docker Compose