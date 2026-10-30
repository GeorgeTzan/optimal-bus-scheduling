export interface StudioTrip {
  id: string;
  tripCode: string;
  resourceId: string;
  startMinutes: number;
  endMinutes: number;
  startStation: string;
  endStation: string;
  isLocked: boolean;
  hasViolation?: boolean;
  violationMessage?: string;
  distanceKm?: number;
  roadType?: string;
  allowedBusTypes?: string[];
}

export interface StudioResource {
  id: string;
  code: string;
  driverName: string;
  busPlate: string;
  homeStation: string;
}

export interface StudioRevision {
  revisionId: string;
  version: number;
  status: "draft" | "approval_requested" | "approved" | "published";
  author: string;
  comment?: string;
  updatedAt: string;
}

export interface StudioFilters {
  searchQuery: string;
  station: string;
  onlyLocked: boolean;
  onlyViolations: boolean;
}
