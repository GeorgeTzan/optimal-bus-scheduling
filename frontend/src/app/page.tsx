"use client";

import { useEffect, useState } from "react";

interface Trip {
  id: string;
  startStation: string;
  endStation: string;
  time: {
    start: string;
    end: string;
    durationMinutes: number;
  };
  classification: {
    group: string;
    roadType: string;
    allowedBusTypes: string[];
    specificBusOverrides: string[];
  };
  properties: {
    distance: number;
    alternativeStationCodes: string[];
    constraints: {
      shiftPosition: string;
      nextDayRestRule: string;
      daysToRestRule: number;
    };
  };
}

interface Driver {
  driverId: string;
  busId: string;
  homeStation: string;
  currentStation: string;
  shiftStartTime: string;
  busAttributes: {
    type: string;
    isKtel: number;
    excludeFromEq: number;
    distanceAdjustment: number;
  };
  preassignedBreaks: Array<{
    durationMinutes: number;
    dayIndex: number;
  }>;
  parameters: {
    cost: number;
    compatibility: string;
  };
}

type TabType = 'trips' | 'drivers' | 'solver';

interface BusState {
  busId: string;
  homeStation: string;
  currentStation: string;
  availableAt: number;
  assignedTrips: string[];
  transfers: Array<{
    type: string;
    fromStation: string;
    toStation: string;
    startMinutes: number;
    endMinutes: number;
    duration: number;
  }>;
  totalIdleTime: number;
  totalDrivingTime: number;
}

interface SolutionAssignment {
  tripId: string;
  busId: string;
  idleTime: number;
}

interface SolutionMetrics {
  totalTrips: number;
  assigned: number;
  unassigned: number;
  busesUsed: number;
  totalIdleTime: number;
  totalDrivingTime: number;
  totalTransferTime?: number;
  baseMismatchCount?: number;
  sequencesProcessed: number;
}

interface Solution {
  assignments: SolutionAssignment[];
  busStates: BusState[];
  unusedBuses: BusState[];
  unassignedTrips: string[];
  metrics: SolutionMetrics;
}

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabType>('trips');
  const [trips, setTrips] = useState<Trip[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [selectedTrip, setSelectedTrip] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [driverPage, setDriverPage] = useState(1);
  const [solution, setSolution] = useState<Solution | null>(null);
  const [isSolving, setIsSolving] = useState(false);
  const [solverPage, setSolverPage] = useState(1);
  const [solverSelectedTrip, setSolverSelectedTrip] = useState<Trip | null>(null);
  const [solverSelectedBus, setSolverSelectedBus] = useState<string | null>(null);
  const tripsPerPage = 5;
  const driversPerPage = 10;

  useEffect(() => {
    fetch("/api/trips")
      .then((res) => res.json())
      .then((data) => {
        setTrips(data.trips);
      })
      .catch((err) => console.error("Failed to load trips:", err));

    fetch("/api/drivers")
      .then((res) => res.json())
      .then((data) => {
        setDrivers(data.drivers);
      })
      .catch((err) => console.error("Failed to load drivers:", err));
  }, []);

  const filteredTrips = trips.filter((trip) => {
    const lowerFilter = searchFilter.toLowerCase();
    const idMatch = trip.id.toLowerCase().includes(lowerFilter);
    const startMatch = trip.startStation.toLowerCase().includes(lowerFilter);
    const endMatch = trip.endStation.toLowerCase().includes(lowerFilter);

    if (lowerFilter.startsWith("stn ")) {
      const station = lowerFilter.slice(4);
      return startMatch || endMatch || trip.startStation.toLowerCase().includes(station) || trip.endStation.toLowerCase().includes(station);
    }

    if (lowerFilter.startsWith("from ")) {
      const station = lowerFilter.slice(5);
      return trip.startStation.toLowerCase().includes(station);
    }

    if (lowerFilter.startsWith("to ")) {
      const station = lowerFilter.slice(3);
      return trip.endStation.toLowerCase().includes(station);
    }

    return idMatch || startMatch || endMatch;
  });

  const totalPages = Math.ceil(filteredTrips.length / tripsPerPage);
  const startIndex = (currentPage - 1) * tripsPerPage;
  const paginatedTrips = filteredTrips.slice(startIndex, startIndex + tripsPerPage);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    setSelectedTrip(null); 
  };

  const timeToPixels = (minutes: number): number => {
    return (minutes / (24 * 60)) * 100;
  };

  const timeStringToMinutes = (timeStr: string): number => {
    const [hours, minutes] = timeStr.split(':').map(Number);
    return (hours || 0) * 60 + (minutes || 0);
  };

  const calculateDuration = (startMinutes: number, endMinutes: number) => {
    if (endMinutes < startMinutes) {
      return endMinutes - startMinutes + 1440; 
    }
    return endMinutes - startMinutes;
  };

  const formatDuration = (minutes: number): string => {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    if (hours > 0) {
      return `${hours}h ${mins}m`;
    } else {
      return `0h:${mins}m`;
    }
  };


  const downloadTripsAsJson = () => {
    const dataStr = JSON.stringify(filteredTrips, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    const exportFileDefaultName = 'trips.json';
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
  };

  const stationColor = (station: string): string => {
    const stationColors = {
      blue: "#3b82f6",
      green: "#10b981",
      red: "#ef4444",
      purple: "#8b5cf6",
      yellow: "#eab308",
      orange: "#f97316",
      indigo: "#6366f1",
      cyan: "#06b6d4",
      pink: "#ec4899",
      teal: "#14b8a6",
      lime: "#84cc16",
      amber: "#f59e0b"
    };
    const colorKeys = Object.keys(stationColors);
    const hash = station.split('').reduce((acc, char) => {
        acc = ((acc << 5) - acc) + char.charCodeAt(0);
        return acc & acc;
    }, 0);
    const index = Math.abs(hash) % colorKeys.length;
    return colorKeys[index] || 'blue';
  };

  const getColor = (trip: Trip): { start: string, end: string } => {
    const startColorName = stationColor(trip.startStation);
    const endColorName = stationColor(trip.endStation);
    const stationColors = {
      blue: "#3b82f6",
      green: "#10b981",
      red: "#ef4444",
      purple: "#8b5cf6",
      yellow: "#eab308",
      orange: "#f97316",
      indigo: "#6366f1",
      cyan: "#06b6d4",
      pink: "#ec4899",
      teal: "#14b8a6",
      lime: "#84cc16",
      amber: "#f59e0b"
    };
    return {
      start: stationColors[startColorName as keyof typeof stationColors],
      end: stationColors[endColorName as keyof typeof stationColors]
    };
  };

  const calculatePeakHour = (trips: Trip[]): string => {
    if (trips.length === 0) return "N/A";
    const hourCounts: { [key: number]: number } = {};
    trips.forEach((trip) => {
      const startMinutes = timeStringToMinutes(trip.time.start);
      const hour = Math.floor(startMinutes / 60);
      hourCounts[hour] = (hourCounts[hour] || 0) + 1;
    });
    const peakHour = Object.keys(hourCounts).reduce((a, b) =>
      (hourCounts[Number(a)] || 0) > (hourCounts[Number(b)] || 0) ? a : b
    );
    const hourNum = Number(peakHour);
    const ampm = hourNum < 12 ? 'AM' : 'PM';
    const displayHour = hourNum === 0 ? 12 : hourNum > 12 ? hourNum - 12 : hourNum;
    return `${displayHour} ${ampm}`;
  };

  const calculateOperatingWindow = (trips: Trip[]): string => {
    if (trips.length === 0) return "N/A";
    const startMinutes = trips.map(t => timeStringToMinutes(t.time.start));
    const endMinutes = trips.map(t => {
      const end = timeStringToMinutes(t.time.end);
      const start = timeStringToMinutes(t.time.start);
      return end < start ? end + 1440 : end;
    });
    const minStart = Math.min(...startMinutes);
    const maxEnd = Math.max(...endMinutes);
    const formatTime = (minutes: number): string => {
      const hour = Math.floor(minutes / 60) % 24;
      const ampm = hour < 12 ? 'AM' : 'PM';
      const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
      return `${displayHour} ${ampm}`;
    };
    return `${formatTime(minStart)} - ${formatTime(maxEnd)}`;
  };

  const hourLabels = Array.from({ length: 25 }, (_, i) => i);

  const [solverMode, setSolverMode] = useState<'greedy' | 'sa'>('greedy');
  const [saIters, setSaIters] = useState(4000);
  const [saTemp, setSaTemp] = useState(50);
  const [saCooling, setSaCooling] = useState(0.999);
  const [solutionHistory, setSolutionHistory] = useState<{ name: string; solution: Solution }[]>([]);
  const [lahcSolution, setLahcSolution] = useState<Solution | null>(null);

  const runConstructiveHeuristic = async () => {
    setIsSolving(true);
    try {
      const response = await fetch("/api/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: solverMode,
          sa_iters: saIters,
          sa_temp: saTemp,
          sa_cooling: saCooling,
        }),
      });
      const data = await response.json();
      setSolution(data);
      setSolutionHistory(prev => [...prev.filter(s => s.name !== solverMode), { name: solverMode === 'sa' ? 'Simulated Annealing' : 'Greedy Heuristic', solution: data }]);
    } catch (err) {
      console.error("Failed to run solver:", err);
    } finally {
      setIsSolving(false);
    }
  };

  const loadLegacySolution = async () => {
    setIsSolving(true);
    try {
      const response = await fetch("/api/solve/legacy", { method: "POST" });
      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }
      const data = await response.json();
      setSolution(data);
      setSolutionHistory(prev => [...prev.filter(s => s.name !== 'Legacy CV'), { name: 'Legacy CV', solution: data }]);
    } catch (err) {
      console.error("Failed to load legacy solution:", err);
    } finally {
      setIsSolving(false);
    }
  };

  const runLAHC = async (fromCurrent = false) => {
    setIsSolving(true);
    try {
      const body = fromCurrent && lahcSolution ? { previous_solution: lahcSolution } : {};
      const response = await fetch("/api/solve/lahc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`Server error: ${response.status}`);
      const data = await response.json();
      setLahcSolution(data);
      setSolution(data);
      setSolutionHistory(prev => [...prev.filter(s => s.name !== 'LAHC'), { name: 'LAHC', solution: data }]);
    } catch (err) {
      console.error("Failed to run LAHC:", err);
    } finally {
      setIsSolving(false);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-900 via-slate-800 to-slate-900 p-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex items-center gap-3">
          <div className="bg-white/10 p-3 rounded-lg">
            <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 24 24">
              <path d="M17 20H7V21C7 21.5523 6.55228 22 6 22H5C4.44772 22 4 21.5523 4 21V12.5L3.05279 12C2.44699 11.6667 2.23944 10.8946 2.58209 10.2953L3.13795 9.28632C3.59439 8.48303 4.17814 7.77229 4.85967 7.17837L6.5 5.5C7.5 4.5 8 4 10 4H14C16 4 16.5 4.5 17.5 5.5L19.1403 7.17837C19.8219 7.77229 20.4056 8.48303 20.8621 9.28632L21.4179 10.2953C21.7606 10.8946 21.553 11.6667 20.9472 12L20 12.5V21C20 21.5523 19.5523 22 19 22H18C17.4477 22 17 21.5523 17 21V20ZM5 12V18H19V12H5ZM7.5 13C8.32843 13 9 13.6716 9 14.5C9 15.3284 8.32843 16 7.5 16C6.67157 16 6 15.3284 6 14.5C6 13.6716 6.67157 13 7.5 13ZM16.5 13C17.3284 13 18 13.6716 18 14.5C18 15.3284 17.3284 16 16.5 16C15.6716 16 15 15.3284 15 14.5C15 13.6716 15.6716 13 16.5 13ZM5.41603 10H18.584L17.8727 8.8639C17.5199 8.31389 17.0698 7.83084 16.5429 7.44114L15.5 6.5C15 6 14.5 6 14 6H10C9.5 6 9 6 8.5 6.5L7.45711 7.44114C6.93023 7.83084 6.48007 8.31389 6.12733 8.8639L5.41603 10Z"/>
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white">Bus Schedule Visualization</h1>
        </div>

        {/* Tabs Navigation */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setActiveTab('trips')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition flex items-center gap-2 ${
              activeTab === 'trips'
                ? 'bg-white/20 text-white'
                : 'bg-white/5 text-slate-300 hover:bg-white/10'
            }`}
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M17 20H7V21C7 21.5523 6.55228 22 6 22H5C4.44772 22 4 21.5523 4 21V12.5L3.05279 12C2.44699 11.6667 2.23944 10.8946 2.58209 10.2953L3.13795 9.28632C3.59439 8.48303 4.17814 7.77229 4.85967 7.17837L6.5 5.5C7.5 4.5 8 4 10 4H14C16 4 16.5 4.5 17.5 5.5L19.1403 7.17837C19.8219 7.77229 20.4056 8.48303 20.8621 9.28632L21.4179 10.2953C21.7606 10.8946 21.553 11.6667 20.9472 12L20 12.5V21C20 21.5523 19.5523 22 19 22H18C17.4477 22 17 21.5523 17 21V20ZM5 12V18H19V12H5ZM7.5 13C8.32843 13 9 13.6716 9 14.5C9 15.3284 8.32843 16 7.5 16C6.67157 16 6 15.3284 6 14.5C6 13.6716 6.67157 13 7.5 13ZM16.5 13C17.3284 13 18 13.6716 18 14.5C18 15.3284 17.3284 16 16.5 16C15.6716 16 15 15.3284 15 14.5C15 13.6716 15.6716 13 16.5 13ZM5.41603 10H18.584L17.8727 8.8639C17.5199 8.31389 17.0698 7.83084 16.5429 7.44114L15.5 6.5C15 6 14.5 6 14 6H10C9.5 6 9 6 8.5 6.5L7.45711 7.44114C6.93023 7.83084 6.48007 8.31389 6.12733 8.8639L5.41603 10Z"/>
            </svg>
            Trips/Δρομολόγια
          </button>
          <button
            onClick={() => setActiveTab('drivers')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition flex items-center gap-2 ${
              activeTab === 'drivers'
                ? 'bg-white/20 text-white'
                : 'bg-white/5 text-slate-300 hover:bg-white/10'
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
            Drivers/Οδηγοί
          </button>
          <button
            onClick={() => setActiveTab('solver')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition flex items-center gap-2 ${
              activeTab === 'solver'
                ? 'bg-white/20 text-white'
                : 'bg-white/5 text-slate-300 hover:bg-white/10'
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Solver/Επιλυτής
          </button>
        </div>

        {/* Trips Tab Content */}
        {activeTab === 'trips' && (
          <>
            <div className="bg-white/10 backdrop-blur-sm rounded-lg p-3 mb-4 border border-white/10">
              <div className="flex gap-3">
                <div className="flex-1 relative">
                  <svg className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Search trips by ID or station..."
                    value={searchFilter}
                    onChange={(e) => {
                      setSearchFilter(e.target.value);
                      setCurrentPage(1);  
                    }}
                    className="w-full pl-10 pr-4 py-2 rounded-lg bg-white/5 text-white placeholder-slate-400 border border-white/10 focus:outline-none focus:border-blue-400 transition text-sm"
                  />
                </div>
                <button
                  onClick={downloadTripsAsJson}
                  className="px-4 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-purple-700 text-white hover:from-purple-500 hover:to-purple-600 transition text-sm font-medium"
                >
                  Save as JSON
                </button>
              </div>
            </div>

        <div className="bg-slate-900/80 backdrop-blur-sm rounded-lg overflow-hidden border border-white/10">
          <div className="overflow-x-auto">
            <div className="min-w-max">
              <div className="sticky top-0 z-10 bg-slate-950/90 border-b border-white/10">
                <div className="flex">
                  <div className="w-44 px-3 py-3 border-r border-white/10 flex items-end">
                    <span className="text-slate-300 text-xs font-semibold uppercase tracking-wide">Route Info</span>
                  </div>
                  <div className="flex-1 px-3 py-3">
                    <div className="flex h-10">
                      {hourLabels.map((hour) => (
                        <div
                          key={hour}
                          className="flex-1 text-center border-r border-white/5 text-xs text-slate-500 font-mono"
                        >
                          {String(hour).padStart(2, "0")}:00
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-slate-900/50">
                {filteredTrips.length === 0 ? (
                  <div className="h-24 flex items-center justify-center text-slate-500 text-sm">
                    {searchFilter ? "No trips found matching your search" : "Loading trips..."}
                  </div>
                ) : (
                  paginatedTrips.map((trip, idx) => {
                    const isSelected = selectedTrip === trip.id;
                    const startMinutes = timeStringToMinutes(trip.time.start);
                    const endMinutes = timeStringToMinutes(trip.time.end);
                    const durationMinutes = calculateDuration(startMinutes, endMinutes);
                    const leftPercent = timeToPixels(startMinutes);
                    const widthPercent = timeToPixels(durationMinutes);

                    return (
                      <div
                        key={idx}
                        className={`border-b border-white/5 transition-all cursor-pointer hover:bg-white/5 ${
                          isSelected ? "bg-white/10" : ""
                        }`}
                        onClick={() =>
                          setSelectedTrip(isSelected ? null : trip.id)
                        }
                      >
                        <div className="flex">
                          <div className="w-44 px-3 py-2.5 border-r border-white/10 bg-slate-900/50">
                            <div className="font-semibold text-white text-xs mb-1.5">
                              {trip.id}
                            </div>
                            <div className="text-xs text-slate-400 space-y-0.5">
                              <div>
                                <span className="text-slate-500">From:</span> <span className="text-slate-300">Stn {trip.startStation}</span>
                              </div>
                              <div>
                                <span className="text-slate-500">To:</span> <span className="text-slate-300">Stn {trip.endStation}</span>
                              </div>
                              <div className="pt-1 mt-1 border-t border-white/5">
                                <span className="text-slate-300 font-mono text-xs">
                                  {trip.time.start} → {trip.time.end}
                                </span>
                              </div>
                            </div>
                          </div>

                          <div className="flex-1 relative px-3 py-2.5">
                            <div className="relative h-12 bg-slate-950/40 rounded overflow-hidden">
                              <div className="absolute inset-0 flex">
                                {hourLabels.map((hour) => (
                                  <div
                                    key={hour}
                                    className="flex-1 border-r border-white/5"
                                  />
                                ))}
                              </div>

                              <div
                                className="absolute top-1.5 bottom-1.5 rounded shadow-md transition-all transform hover:scale-y-105 hover:shadow-lg border border-white/30"
                                style={{
                                  background: `linear-gradient(to right, ${getColor(trip).start}, ${getColor(trip).end})`,
                                  left: `${leftPercent}%`,
                                  width: `${Math.max(widthPercent, 2)}%`,
                                }}
                              >
                                <div className="h-full px-2 flex items-center justify-between overflow-visible">
                                  <span className="text-white text-xs font-semibold whitespace-nowrap">
                                    {trip.id}
                                  </span>
                                  <span className="text-white/90 text-xs ml-1.5 whitespace-nowrap">
                                    {formatDuration(durationMinutes)}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>

                        {isSelected && (
                          <div className="bg-blue-900/20 border-t border-blue-500/20 px-3 py-2">
                            <div className="grid grid-cols-4 gap-3 text-xs">
                              <div>
                                <span className="text-slate-400">Duration</span>
                                <div className="text-blue-300 font-semibold">
                                  {formatDuration(durationMinutes)}
                                </div>
                              </div>
                              <div>
                                <span className="text-slate-400">Departure</span>
                                <div className="text-blue-300 font-semibold">
                                  {trip.time.start}
                                </div>
                              </div>
                              <div>
                                <span className="text-slate-400">Arrival</span>
                                <div className="text-blue-300 font-semibold">
                                  {trip.time.end}
                                </div>
                              </div>
                              <div>
                                <span className="text-slate-400">Progress</span>
                                <div className="text-blue-300 font-semibold">
                                  Not assigned
                                </div>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3 mt-4">
          <div className="bg-gradient-to-br from-blue-600/20 to-blue-700/20 backdrop-blur-sm rounded-lg p-3 border border-blue-500/20">
            <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Total Routes</div>
            <div className="text-3xl font-bold text-blue-300">{filteredTrips.length}</div>
          </div>
          <div className="bg-gradient-to-br from-green-600/20 to-green-700/20 backdrop-blur-sm rounded-lg p-3 border border-green-500/20">
            <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Operating Window</div>
            <div className="text-lg font-semibold text-green-300">{calculateOperatingWindow(trips)}</div>
          </div>
          <div className="bg-gradient-to-br from-purple-600/20 to-purple-700/20 backdrop-blur-sm rounded-lg p-3 border border-purple-500/20">
            <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Avg Duration</div>
            <div className="text-2xl font-bold text-purple-300">
              {filteredTrips.length > 0
                ? formatDuration(
                    Math.round(
                      filteredTrips.reduce(
                        (acc, t) => acc + calculateDuration(
                          timeStringToMinutes(t.time.start),
                          timeStringToMinutes(t.time.end)
                        ),
                        0
                      ) / filteredTrips.length
                    )
                  )
                : "0h:0m"}
            </div>
          </div>
          <div className="bg-gradient-to-br from-orange-600/20 to-orange-700/20 backdrop-blur-sm rounded-lg p-3 border border-orange-500/20">
            <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Peak Hour</div>
            <div className="text-lg font-semibold text-orange-300">{calculatePeakHour(trips)}</div>
          </div>
        </div>

            {totalPages > 1 && (
              <div className="flex justify-center items-center mt-4 space-x-2">
                <button
                  onClick={() => handlePageChange(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="px-3 py-1.5 bg-white/10 text-white rounded text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/20 transition border border-white/10"
                >
                  Previous
                </button>
                <span className="text-slate-400 text-sm">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => handlePageChange(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1.5 bg-white/10 text-white rounded text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/20 transition border border-white/10"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}

        {/* Drivers Tab */}
        {activeTab === 'drivers' && (
          <div className="space-y-4">
            <div className="grid grid-cols-4 gap-3">
              <div className="bg-gradient-to-br from-blue-600/20 to-blue-700/20 backdrop-blur-sm rounded-lg p-3 border border-blue-500/20">
                <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Total Drivers</div>
                <div className="text-3xl font-bold text-blue-300">{drivers.length}</div>
              </div>
              <div className="bg-gradient-to-br from-green-600/20 to-green-700/20 backdrop-blur-sm rounded-lg p-3 border border-green-500/20">
                <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">KTEL Buses</div>
                <div className="text-3xl font-bold text-green-300">
                  {drivers.filter(d => d.busAttributes.isKtel === 1).length}
                </div>
              </div>
              <div className="bg-gradient-to-br from-purple-600/20 to-purple-700/20 backdrop-blur-sm rounded-lg p-3 border border-purple-500/20">
                <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Avg Cost</div>
                <div className="text-2xl font-bold text-purple-300">
                  {drivers.length > 0
                    ? Math.round(drivers.reduce((acc, d) => acc + d.parameters.cost, 0) / drivers.length)
                    : 0}
                </div>
              </div>
              <div className="bg-gradient-to-br from-orange-600/20 to-orange-700/20 backdrop-blur-sm rounded-lg p-3 border border-orange-500/20">
                <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Bus Types</div>
                <div className="text-2xl font-bold text-orange-300">
                  {new Set(drivers.map(d => d.busAttributes.type)).size}
                </div>
              </div>
            </div>

            <div className="bg-slate-900/80 backdrop-blur-sm rounded-lg overflow-hidden border border-white/10">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-950/90 border-b border-white/10">
                    <tr>
                      <th className="px-3 py-2.5 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">Driver ID</th>
                      <th className="px-3 py-2.5 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">Bus ID</th>
                      <th className="px-3 py-2.5 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">Home Station</th>
                      <th className="px-3 py-2.5 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">Bus Type</th>
                      <th className="px-3 py-2.5 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">KTEL</th>
                      <th className="px-3 py-2.5 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">Cost</th>
                      <th className="px-3 py-2.5 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">Breaks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {drivers
                      .slice((driverPage - 1) * driversPerPage, driverPage * driversPerPage)
                      .map((driver, idx) => (
                        <tr
                          key={idx}
                          className="border-b border-white/5 hover:bg-white/5 transition"
                        >
                          <td className="px-3 py-2 text-white font-mono text-xs">{driver.driverId}</td>
                          <td className="px-3 py-2 text-slate-300 font-mono text-xs">{driver.busId}</td>
                          <td className="px-3 py-2 text-slate-300 text-xs">Station {driver.homeStation}</td>
                          <td className="px-3 py-2 text-slate-300 text-xs">
                            <span className="px-2 py-0.5 bg-blue-600/30 text-blue-300 rounded text-xs">
                              {driver.busAttributes.type}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-slate-300 text-xs">
                            {driver.busAttributes.isKtel === 1 ? (
                              <span className="px-2 py-0.5 bg-green-600/30 text-green-300 rounded text-xs">Yes</span>
                            ) : (
                              <span className="px-2 py-0.5 bg-gray-600/30 text-gray-300 rounded text-xs">No</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-slate-300 font-semibold text-xs">{driver.parameters.cost}</td>
                          <td className="px-3 py-2 text-slate-300 text-xs">
                            {driver.preassignedBreaks.filter(b => b.durationMinutes > 0).length}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>

            {Math.ceil(drivers.length / driversPerPage) > 1 && (
              <div className="flex justify-center items-center space-x-2">
                <button
                  onClick={() => setDriverPage(driverPage - 1)}
                  disabled={driverPage === 1}
                  className="px-3 py-1.5 bg-white/10 text-white rounded text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/20 transition border border-white/10"
                >
                  Previous
                </button>
                <span className="text-slate-400 text-sm">
                  Page {driverPage} of {Math.ceil(drivers.length / driversPerPage)}
                </span>
                <button
                  onClick={() => setDriverPage(driverPage + 1)}
                  disabled={driverPage === Math.ceil(drivers.length / driversPerPage)}
                  className="px-3 py-1.5 bg-white/10 text-white rounded text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/20 transition border border-white/10"
                >
                  Next
                </button>
              </div>
            )}

            <div className="bg-slate-900/80 backdrop-blur-sm rounded-lg p-4 border border-white/10">
              <h3 className="text-lg font-semibold text-white mb-3">Bus Type Distribution</h3>
              <div className="space-y-2.5">
                {Array.from(new Set(drivers.map(d => d.busAttributes.type))).map((type, idx) => {
                  const count = drivers.filter(d => d.busAttributes.type === type).length;
                  const percentage = (count / drivers.length) * 100;
                  return (
                    <div key={idx}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-slate-300 font-medium">Type {type}</span>
                        <span className="text-slate-400">{count} drivers ({percentage.toFixed(1)}%)</span>
                      </div>
                      <div className="w-full bg-slate-950/50 rounded-full h-1.5">
                        <div
                          className="bg-gradient-to-r from-blue-500 to-purple-500 h-1.5 rounded-full transition-all"
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="bg-slate-900/80 backdrop-blur-sm rounded-lg p-4 border border-white/10">
              <h3 className="text-lg font-semibold text-white mb-3">Drivers by Home Station</h3>
              <div className="grid grid-cols-3 gap-3">
                {Array.from(new Set(drivers.map(d => d.homeStation))).sort().map((station, idx) => {
                  const count = drivers.filter(d => d.homeStation === station).length;
                  return (
                    <div key={idx} className="bg-white/5 backdrop-blur-sm rounded-lg p-3 border border-white/10">
                      <div className="text-slate-400 text-xs mb-1 uppercase tracking-wide">Station {station}</div>
                      <div className="text-2xl font-bold text-blue-300">{count}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'solver' && (
          <div className="space-y-4">
            <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4 border border-white/10">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-white">Constructive Heuristic Solver</h3>
                  <p className="text-slate-400 text-sm mt-1">Assigns trips to buses minimizing idle time between consecutive trips</p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-300 text-xs">Mode</span>
                    <select
                      value={solverMode}
                      onChange={(e) => setSolverMode(e.target.value as 'greedy' | 'sa')}
                      className="bg-white/5 text-white text-xs rounded-lg px-2 py-1 border border-white/10 focus:outline-none"
                      disabled={isSolving}
                    >
                      <option value="greedy">Greedy</option>
                      <option value="sa">SA (optimize)</option>
                    </select>
                  </div>

                  {solverMode === 'sa' && (
                    <div className="flex items-center gap-2">
                      <span className="text-slate-300 text-xs">iters</span>
                      <input
                        type="number"
                        min={1}
                        max={200000}
                        value={saIters}
                        onChange={(e) => setSaIters(Math.max(1, Math.min(200000, Number(e.target.value) || 1)))}
                        className="w-24 bg-white/5 text-white text-xs rounded-lg px-2 py-1 border border-white/10 focus:outline-none"
                        disabled={isSolving}
                      />
                      <span className="text-slate-300 text-xs">temp</span>
                      <input
                        type="number"
                        step={0.1}
                        min={0.1}
                        value={saTemp}
                        onChange={(e) => setSaTemp(Math.max(0.1, Number(e.target.value) || 0.1))}
                        className="w-20 bg-white/5 text-white text-xs rounded-lg px-2 py-1 border border-white/10 focus:outline-none"
                        disabled={isSolving}
                      />
                      <span className="text-slate-300 text-xs">cool</span>
                      <input
                        type="number"
                        step={0.0001}
                        min={0.9}
                        max={0.999999}
                        value={saCooling}
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          setSaCooling(Number.isFinite(v) ? Math.max(0.9, Math.min(0.999999, v)) : 0.999);
                        }}
                        className="w-24 bg-white/5 text-white text-xs rounded-lg px-2 py-1 border border-white/10 focus:outline-none"
                        disabled={isSolving}
                      />
                    </div>
                  )}

                </div>

                <button
                  onClick={runConstructiveHeuristic}
                  disabled={isSolving || trips.length === 0 || drivers.length === 0}
                  className="px-6 py-2.5 rounded-lg bg-gradient-to-r from-green-600 to-green-700 text-white hover:from-green-500 hover:to-green-600 transition text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {isSolving ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Solving...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Run Solver
                    </>
                  )}
                </button>

                <button
                  onClick={loadLegacySolution}
                  disabled={isSolving || trips.length === 0 || drivers.length === 0}
                  className="px-6 py-2.5 rounded-lg bg-gradient-to-r from-blue-600 to-blue-700 text-white hover:from-blue-500 hover:to-blue-600 transition text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                   <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" />
                   </svg>
                   Load CV (Legacy)
                </button>

                <button
                  onClick={() => runLAHC(false)}
                  disabled={isSolving || trips.length === 0 || drivers.length === 0}
                  className="px-6 py-2.5 rounded-lg bg-gradient-to-r from-violet-600 to-violet-700 text-white hover:from-violet-500 hover:to-violet-600 transition text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {isSolving ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Solving...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      Run LAHC
                    </>
                  )}
                </button>

                {lahcSolution && (
                  <button
                    onClick={() => runLAHC(true)}
                    disabled={isSolving}
                    className="px-6 py-2.5 rounded-lg bg-gradient-to-r from-amber-600 to-amber-700 text-white hover:from-amber-500 hover:to-amber-600 transition text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    {isSolving ? (
                      <>
                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Solving...
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        Re-solve (LAHC)
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>

            {solutionHistory.length > 1 && (
              <div className="bg-slate-900/80 backdrop-blur-sm rounded-lg p-4 border border-white/10">
                <h3 className="text-lg font-semibold text-white mb-3">Solution Comparison</h3>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-slate-950/90 border-b border-white/10">
                      <tr>
                        <th className="px-3 py-2 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">Heuristic</th>
                        <th className="px-3 py-2 text-right text-slate-300 text-xs font-semibold uppercase tracking-wide">Assigned</th>
                        <th className="px-3 py-2 text-right text-slate-300 text-xs font-semibold uppercase tracking-wide">Idle Time</th>
                        <th className="px-3 py-2 text-right text-slate-300 text-xs font-semibold uppercase tracking-wide">Buses Used</th>
                        <th className="px-3 py-2 text-right text-slate-300 text-xs font-semibold uppercase tracking-wide">Base Mismatches</th>
                        <th className="px-3 py-2 text-center text-slate-300 text-xs font-semibold uppercase tracking-wide">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {solutionHistory.map((hist, idx) => (
                        <tr key={idx} className={`border-b border-white/5 hover:bg-white/5 transition ${solution?.metrics === hist.solution.metrics ? 'bg-blue-500/10' : ''}`}>
                          <td className="px-3 py-3 text-white font-medium text-sm">{hist.name}</td>
                          <td className="px-3 py-3 text-right text-blue-300 font-mono text-sm">{hist.solution.metrics.assigned}</td>
                          <td className="px-3 py-3 text-right text-purple-300 font-mono text-sm">{formatDuration(hist.solution.metrics.totalIdleTime)}</td>
                          <td className="px-3 py-3 text-right text-green-300 font-mono text-sm">{hist.solution.metrics.busesUsed}</td>
                          <td className="px-3 py-3 text-right text-red-300 font-mono text-sm">{hist.solution.metrics.baseMismatchCount || 0}</td>
                          <td className="px-3 py-3 text-center">
                            <button 
                              onClick={() => setSolution(hist.solution)}
                              className="px-2 py-1 bg-white/10 hover:bg-white/20 text-white rounded text-xs transition"
                            >
                              View
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {solution && (
              <>
                <div className="grid grid-cols-5 gap-3">
                  <div className="bg-gradient-to-br from-blue-600/20 to-blue-700/20 backdrop-blur-sm rounded-lg p-3 border border-blue-500/20">
                    <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Trips Assigned</div>
                    <div className="text-3xl font-bold text-blue-300">{solution.metrics.assigned}</div>
                  </div>
                  <div className="bg-gradient-to-br from-green-600/20 to-green-700/20 backdrop-blur-sm rounded-lg p-3 border border-green-500/20">
                    <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Buses Used</div>
                    <div className="text-3xl font-bold text-green-300">{solution.metrics.busesUsed}<span className="text-lg text-green-400">/{drivers.length}</span></div>
                  </div>
                  <div className="bg-gradient-to-br from-purple-600/20 to-purple-700/20 backdrop-blur-sm rounded-lg p-3 border border-purple-500/20">
                    <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Total Idle Time</div>
                    <div className="text-2xl font-bold text-purple-300">{formatDuration(solution.metrics.totalIdleTime)}</div>
                  </div>
                  <div className="bg-gradient-to-br from-orange-600/20 to-orange-700/20 backdrop-blur-sm rounded-lg p-3 border border-orange-500/20">
                    <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Unassigned</div>
                    <div className="text-3xl font-bold text-orange-300">{solution.metrics.unassigned}</div>
                  </div>
                  <div className="bg-gradient-to-br from-cyan-600/20 to-cyan-700/20 backdrop-blur-sm rounded-lg p-3 border border-cyan-500/20">
                    <div className="text-slate-400 text-xs mb-1.5 uppercase tracking-wide">Transfer Time</div>
                    <div className="text-2xl font-bold text-cyan-300">{formatDuration(solution.metrics.totalTransferTime || 0)}</div>
                  </div>
                </div>

                {solution.metrics.baseMismatchCount !== undefined && solution.metrics.baseMismatchCount > 0 && (
                  <div className="bg-red-500/10 border border-red-500/20 p-2 rounded-lg text-xs text-red-300 flex items-center gap-2">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    Warning: {solution.metrics.baseMismatchCount} buses do not finish at their Home Station.
                  </div>
                )}

                <div className="bg-slate-900/80 backdrop-blur-sm rounded-lg p-4 border border-white/10">
                  <h3 className="text-lg font-semibold text-white mb-3">Bus Schedules</h3>
                  <div className="space-y-3">
                    {solution.busStates
                      .sort((a, b) => b.assignedTrips.length - a.assignedTrips.length)
                      .slice((solverPage - 1) * 5, solverPage * 5)
                      .map((bus, idx) => {
                        const driver = drivers.find(d => d.busId === bus.busId);
                        return (
                          <div key={idx} className="bg-white/5 rounded-lg p-3 border border-white/10">
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center gap-3">
                                <span className="text-white font-semibold text-sm">{bus.busId}</span>
                                <span className="text-slate-400 text-xs">Home: Station {driver?.homeStation}</span>
                                <span className="px-2 py-0.5 bg-blue-600/30 text-blue-300 rounded text-xs">
                                  {bus.assignedTrips.length} trips
                                </span>
                              </div>
                              <div className="flex items-center gap-3">
                                <span className="text-green-400 text-xs">Driving: {formatDuration(bus.totalDrivingTime)}</span>
                                <span className="text-slate-400 text-xs">Idle: {formatDuration(bus.totalIdleTime)}</span>
                              </div>
                            </div>
                            <div className="relative h-8 bg-slate-950/40 rounded overflow-hidden">
                              <div className="absolute inset-0 flex">
                                {hourLabels.map((hour) => (
                                  <div key={hour} className="flex-1 border-r border-white/5" />
                                ))}
                              </div>
                              {bus.assignedTrips.map((tripId, tIdx) => {
                                const trip = trips.find(t => t.id === tripId);
                                if (!trip) return null;
                                const startMinutes = timeStringToMinutes(trip.time.start);
                                const endMinutes = timeStringToMinutes(trip.time.end);
                                const durationMinutes = calculateDuration(startMinutes, endMinutes);
                                const leftPercent = timeToPixels(startMinutes);
                                const widthPercent = timeToPixels(durationMinutes);
                                return (
                                  <div
                                    key={tIdx}
                                    className="absolute top-1 bottom-1 rounded text-xs flex items-center justify-center text-white font-medium border border-white/30 hover:brightness-110 hover:shadow-lg transition-all cursor-pointer"
                                    style={{
                                      background: `linear-gradient(to right, ${getColor(trip).start}, ${getColor(trip).end})`,
                                      left: `${leftPercent}%`,
                                      width: `${Math.max(widthPercent, 1.5)}%`,
                                    }}
                                    onClick={() => {
                                      setSolverSelectedTrip(trip);
                                      setSolverSelectedBus(bus.busId);
                                    }}
                                    title="Click for details"
                                  >
                                    <span className="truncate px-1 text-xs">{trip.id}</span>
                                  </div>
                                );
                              })}

                            </div>
                          </div>
                        );
                      })}
                  </div>
                  {Math.ceil(solution.busStates.length / 5) > 1 && (
                    <div className="flex justify-center items-center mt-4 space-x-2">
                      <button
                        onClick={() => setSolverPage(solverPage - 1)}
                        disabled={solverPage === 1}
                        className="px-3 py-1.5 bg-white/10 text-white rounded text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/20 transition border border-white/10"
                      >
                        Previous
                      </button>
                      <span className="text-slate-400 text-sm">
                        Page {solverPage} of {Math.ceil(solution.busStates.length / 5)}
                      </span>
                      <button
                        onClick={() => setSolverPage(solverPage + 1)}
                        disabled={solverPage === Math.ceil(solution.busStates.length / 5)}
                        className="px-3 py-1.5 bg-white/10 text-white rounded text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/20 transition border border-white/10"
                      >
                        Next
                      </button>
                    </div>
                  )}
                </div>

                {solution.unassignedTrips.length > 0 && (
                  <div className="bg-red-900/20 backdrop-blur-sm rounded-lg p-4 border border-red-500/20">
                    <h3 className="text-lg font-semibold text-red-300 mb-3">Unassigned Trips</h3>
                    <div className="flex flex-wrap gap-2">
                      {solution.unassignedTrips.map((tripId, idx) => (
                        <span key={idx} className="px-2 py-1 bg-red-600/30 text-red-300 rounded text-xs">
                          {tripId}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {solution.unusedBuses && solution.unusedBuses.length > 0 && (
                  <div className="bg-yellow-900/20 backdrop-blur-sm rounded-lg p-4 border border-yellow-500/20">
                    <h3 className="text-lg font-semibold text-yellow-300 mb-3">Unused Buses ({solution.unusedBuses.length})</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="bg-slate-950/90 border-b border-white/10">
                          <tr>
                            <th className="px-3 py-2 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">Bus ID</th>
                            <th className="px-3 py-2 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">Home Station</th>
                            <th className="px-3 py-2 text-left text-slate-300 text-xs font-semibold uppercase tracking-wide">Reason</th>
                          </tr>
                        </thead>
                        <tbody>
                          {solution.unusedBuses.map((bus, idx) => {
                            const tripsFromStation = trips.filter(t => t.startStation === bus.homeStation).length;
                            return (
                              <tr key={idx} className="border-b border-white/5">
                                <td className="px-3 py-2 text-white font-mono text-xs">{bus.busId}</td>
                                <td className="px-3 py-2 text-slate-300 text-xs">Station {bus.homeStation}</td>
                                <td className="px-3 py-2 text-yellow-300 text-xs">
                                  {tripsFromStation === 0 
                                    ? "No trips originate from home station" 
                                    : `${tripsFromStation} trips from station but already covered by other buses`}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

              </>
            )}

            {!solution && (
              <div className="bg-slate-900/80 backdrop-blur-sm rounded-lg p-8 border border-white/10 text-center">
                <svg className="w-16 h-16 text-slate-600 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                <h3 className="text-lg font-semibold text-slate-400 mb-2">No Solution Yet</h3>
                <p className="text-slate-500 text-sm">Click "Run Solver" to generate a feasible assignment of trips to buses</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Trip Details Modal */}
      {solverSelectedTrip && (
        <div 
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => {
            setSolverSelectedTrip(null);
            setSolverSelectedBus(null);
          }}
        >
          <div 
            className="bg-slate-900 border border-white/20 rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div 
              className="px-6 py-4 border-b border-white/10"
              style={{
                background: `linear-gradient(to right, ${getColor(solverSelectedTrip).start}, ${getColor(solverSelectedTrip).end})`,
              }}
            >
              <div className="flex justify-between items-center">
                <h3 className="text-xl font-bold text-white">{solverSelectedTrip.id}</h3>
                <button 
                  onClick={() => {
                    setSolverSelectedTrip(null);
                    setSolverSelectedBus(null);
                  }}
                  className="text-white/80 hover:text-white transition"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Modal Content */}
            <div className="px-6 py-4 space-y-4">
              {/* Assigned Bus */}
              {solverSelectedBus && (
                <div className="flex items-center gap-3 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                  <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h8m-8 4h8m-4 4v3m-4-3h8a2 2 0 002-2V7a2 2 0 00-2-2H8a2 2 0 00-2 2v6a2 2 0 002 2z" />
                  </svg>
                  <div>
                    <div className="text-xs text-blue-300 uppercase tracking-wide">Assigned to Bus</div>
                    <div className="text-white font-semibold">{solverSelectedBus}</div>
                  </div>
                </div>
              )}

              {/* Route */}
              <div className="flex items-center gap-3">
                <div className="flex-1 p-3 bg-white/5 border border-white/10 rounded-lg text-center">
                  <div className="text-xs text-slate-400 uppercase tracking-wide mb-1">From</div>
                  <div className="text-white font-semibold">Station {solverSelectedTrip.startStation}</div>
                </div>
                <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
                <div className="flex-1 p-3 bg-white/5 border border-white/10 rounded-lg text-center">
                  <div className="text-xs text-slate-400 uppercase tracking-wide mb-1">To</div>
                  <div className="text-white font-semibold">Station {solverSelectedTrip.endStation}</div>
                </div>
              </div>

              {/* Time */}
              <div className="grid grid-cols-3 gap-3">
                <div className="p-3 bg-white/5 border border-white/10 rounded-lg text-center">
                  <div className="text-xs text-slate-400 uppercase tracking-wide mb-1">Start</div>
                  <div className="text-green-400 font-mono font-semibold">{solverSelectedTrip.time.start}</div>
                </div>
                <div className="p-3 bg-white/5 border border-white/10 rounded-lg text-center">
                  <div className="text-xs text-slate-400 uppercase tracking-wide mb-1">End</div>
                  <div className="text-red-400 font-mono font-semibold">{solverSelectedTrip.time.end}</div>
                </div>
                <div className="p-3 bg-white/5 border border-white/10 rounded-lg text-center">
                  <div className="text-xs text-slate-400 uppercase tracking-wide mb-1">Duration</div>
                  <div className="text-white font-semibold">{formatDuration(solverSelectedTrip.time.durationMinutes)}</div>
                </div>
              </div>

              {/* Classification */}
              <div className="p-3 bg-white/5 border border-white/10 rounded-lg">
                <div className="text-xs text-slate-400 uppercase tracking-wide mb-2">Classification</div>
                <div className="flex flex-wrap gap-2">
                  <span className="px-2 py-1 bg-purple-500/20 text-purple-300 text-xs rounded">
                    Group: {solverSelectedTrip.classification.group}
                  </span>
                  <span className="px-2 py-1 bg-cyan-500/20 text-cyan-300 text-xs rounded">
                    Road: {solverSelectedTrip.classification.roadType}
                  </span>
                </div>
              </div>

              {/* Properties */}
              <div className="p-3 bg-white/5 border border-white/10 rounded-lg">
                <div className="text-xs text-slate-400 uppercase tracking-wide mb-2">Properties</div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Distance:</span>
                    <span className="text-white font-mono">{solverSelectedTrip.properties.distance} km</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Shift:</span>
                    <span className="text-white">{solverSelectedTrip.properties.constraints.shiftPosition}</span>
                  </div>
                </div>
              </div>

              {/* Allowed Bus Types */}
              {solverSelectedTrip.classification.allowedBusTypes.length > 0 && (
                <div className="p-3 bg-white/5 border border-white/10 rounded-lg">
                  <div className="text-xs text-slate-400 uppercase tracking-wide mb-2">Allowed Bus Types</div>
                  <div className="flex flex-wrap gap-1">
                    {solverSelectedTrip.classification.allowedBusTypes.map((type, idx) => (
                      <span key={idx} className="px-2 py-0.5 bg-green-500/20 text-green-300 text-xs rounded">
                        {type}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 bg-slate-950/50 border-t border-white/10">
              <button
                onClick={() => {
                  setSolverSelectedTrip(null);
                  setSolverSelectedBus(null);
                }}
                className="w-full py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}