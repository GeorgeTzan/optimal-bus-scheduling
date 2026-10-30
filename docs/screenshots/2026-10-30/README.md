# Actual application captures

Captured with Google Chrome through Playwright, against the Next.js production build at 127.0.0.1:3000 and real FastAPI/PostgreSQL/CV worker. Seeded account: admin@ktel.gr. No fixture routes were intercepted for these captures. Session-isolation test alone uses controlled network delays and does not produce visual evidence.

Desktop: 1600×1000. Tablet: 768×1024. Mobile: 390×844. Both Greek and English, light and dark modes. Every image represents rendered application components, not a static recreation of the reference images.

- studio-desktop-light.png: overview and timeline
- studio-inspector-light.png: selected trip and actual assignment
- studio-desktop-dark.png: driver grouping and selected trip
- studio-greek-dark.png: Greek localization
- studio-tablet-dark.png: contextual inspector on tablet
- studio-mobile-dark.png: narrow layout with collapsed navigation
- studio-real-cv-candidate.png: persisted result from a real asynchronous bounded CV run
- scheduling-inspector-light.png: server verification after persistence/reload check

Compared with all four original references: retained navy rail, restrained surface hierarchy, compact operational toolbar, summary cards, pastel route blocks, contextual panel and lower records table. Added actual hour grid and sticky, virtualized resource rows. Unsupported mockup data and controls were excluded. Production gaps are documented in ../../IMPLEMENTATION_STATUS.md.
