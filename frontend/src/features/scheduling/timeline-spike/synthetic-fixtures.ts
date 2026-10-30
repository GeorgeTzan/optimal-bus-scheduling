export interface TimelineTrip {
  id: string;
  resourceId: string;
  startMinutes: number;
  endMinutes: number;
  origin: string;
  destination: string;
  isLocked?: boolean;
}

export interface TimelineResource {
  id: string;
  driverName: string;
  busPlate: string;
  homeStation: string;
}

const STATIONS = ["Patras", "Athens", "Thessaloniki", "Ioannina", "Aigio", "Korinthos", "Tripoli"];

export function generateSyntheticDataset(tripCount: number): {
  trips: TimelineTrip[];
  resources: TimelineResource[];
} {
  const resourceCount = Math.max(10, Math.ceil(tripCount / 6));
  const resources: TimelineResource[] = [];

  for (let r = 1; r <= resourceCount; r++) {
    resources.push({
      id: `RES-${r.toString().padStart(3, "0")}`,
      driverName: `Οδηγός ${r}`,
      busPlate: `AXA-${(1000 + r).toString()}`,
      homeStation: STATIONS[r % STATIONS.length] ?? "Patras",
    });
  }

  const trips: TimelineTrip[] = [];
  let currentTrip = 1;

  for (let r = 0; r < resourceCount && currentTrip <= tripCount; r++) {
    const res = resources[r];
    if (!res) continue;

    let minute = 300 + (r % 5) * 30; // Start between 05:00 and 07:30

    while (minute < 1380 && currentTrip <= tripCount) {
      const duration = 90 + ((currentTrip * 17) % 90); // 90 to 180 min
      const originIdx = (r + currentTrip) % STATIONS.length;
      const destIdx = (originIdx + 1) % STATIONS.length;

      trips.push({
        id: `TRIP-${currentTrip.toString().padStart(4, "0")}`,
        resourceId: res.id,
        startMinutes: minute,
        endMinutes: minute + duration,
        origin: STATIONS[originIdx] ?? "Patras",
        destination: STATIONS[destIdx] ?? "Athens",
        isLocked: currentTrip % 10 === 0,
      });

      currentTrip++;
      minute += duration + 30 + ((currentTrip * 13) % 45); // Turnaround / rest
    }
  }

  return { trips, resources };
}
