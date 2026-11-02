# Actual browser captures

Captured from the running production frontend at `127.0.0.1:3000`, backed by the restricted PostgreSQL API and real CV worker. Compared visually with `docs/v2/KTEL_UI_Mockups/ktel_ui_mockups/02_dense_scheduling_studio.png`.

- `studio-canonical-published.png`: disposable customer imports its own records, manually links two trips, confirms a day, generates an actual CV candidate, applies it, publishes and reloads. The inspector and table show frozen real customer labels and registration. Sparse rows reflect the two supplied trips.
- `studio-reference-archive.png`: explicitly opened saved 387-trip reference history. Editing, optimization and publication are disabled; original station codes remain when names were not frozen in that archive.
- `studio-desktop-light.png`, `studio-desktop-dark.png`, `studio-greek-dark.png`, `studio-tablet-dark.png`, `studio-mobile-dark.png`: real disposable two-resource schedule, vehicle/driver grouping, selected inspector and responsive navigation. No invented extra trips or metrics for screenshot density.

Earlier guided import and service-day captures are retained under `../2026-10-31/`.
