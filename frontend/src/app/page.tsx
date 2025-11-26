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

type TabType = 'trips' | 'drivers';

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabType>('trips');
  const [trips, setTrips] = useState<Trip[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [selectedTrip, setSelectedTrip] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [driverPage, setDriverPage] = useState(1);
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

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-8">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="text-5xl font-bold text-white mb-2">Bus Schedule Visualization</h1>
        </div>

        {/* Tabs Navigation */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveTab('trips')}
            className={`px-6 py-3 rounded-lg font-semibold transition ${
              activeTab === 'trips'
                ? 'bg-blue-600 text-white shadow-lg'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            Trips / Δρομολόγια
          </button>
          <button
            onClick={() => setActiveTab('drivers')}
            className={`px-6 py-3 rounded-lg font-semibold transition ${
              activeTab === 'drivers'
                ? 'bg-blue-600 text-white shadow-lg'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            Drivers / Οδηγοί
          </button>
        </div>

        {}
        {activeTab === 'trips' && (
          <>
            <div className="bg-slate-700 rounded-xl p-4 mb-6 shadow-2xl">
              <div className="flex gap-4">
                <input
                  type="text"
                  placeholder="Search: Trip ID, 'stn 001', 'from 001', 'to 001'..."
                  value={searchFilter}
                  onChange={(e) => {
                    setSearchFilter(e.target.value);
                    setCurrentPage(1);  
                  }}
                  className="flex-1 px-4 py-3 rounded-lg bg-slate-600 text-white placeholder-slate-400 border border-slate-500 focus:outline-none focus:border-blue-500 transition"
                />
                <button
                  onClick={downloadTripsAsJson}
                  className="px-4 py-3 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
                >
                  Save as JSON
                </button>
              </div>
            </div>

        <div className="bg-slate-800 rounded-xl shadow-2xl overflow-hidden border border-slate-700">
          <div className="overflow-x-auto">
            <div className="min-w-max">
              <div className="sticky top-0 z-10 bg-gradient-to-r from-slate-900 to-slate-800 border-b border-slate-700">
                <div className="flex">
                  <div className="w-48 px-4 py-4 border-r border-slate-700 flex items-end">
                    <span className="text-slate-400 text-sm font-semibold">Route Info</span>
                  </div>
                  <div className="flex-1 px-4 py-4">
                    <div className="flex h-12">
                      {hourLabels.map((hour) => (
                        <div
                          key={hour}
                          className="flex-1 text-center border-r border-slate-700 text-xs text-slate-400 font-mono"
                        >
                          {String(hour).padStart(2, "0")}:00
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-slate-800">
                {filteredTrips.length === 0 ? (
                  <div className="h-32 flex items-center justify-center text-slate-400">
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
                        className={`border-b border-slate-700 transition-all cursor-pointer hover:bg-slate-700/50 ${
                          isSelected ? "bg-slate-700/80" : ""
                        }`}
                        onClick={() =>
                          setSelectedTrip(isSelected ? null : trip.id)
                        }
                      >
                        <div className="flex">
                          <div className="w-48 px-4 py-4 border-r border-slate-700 bg-slate-800/50">
                            <div className="font-bold text-white text-sm mb-1">
                              {trip.id}
                            </div>
                            <div className="text-xs text-slate-400 space-y-1">
                              <div>
                                <span className="text-slate-500">From:</span> Stn {trip.startStation}
                              </div>
                              <div>
                                <span className="text-slate-500">To:</span> Stn {trip.endStation}
                              </div>
                              <div className="pt-1 mt-1 border-t border-slate-600">
                                <span className="text-slate-300 font-mono">
                                  {trip.time.start} → {trip.time.end}
                                </span>
                              </div>
                            </div>
                          </div>

                          <div className="flex-1 relative px-4 py-4">
                            <div className="relative h-16 bg-slate-700/30 rounded-lg overflow-hidden">
                              <div className="absolute inset-0 flex">
                                {hourLabels.map((hour) => (
                                  <div
                                    key={hour}
                                    className="flex-1 border-r border-slate-700/20"
                                  />
                                ))}
                              </div>

                              <div
                                className="absolute top-2 bottom-2 rounded-lg shadow-lg transition-all transform hover:scale-y-110 hover:shadow-xl border border-white/20"
                                style={{
                                  background: `linear-gradient(to right, ${getColor(trip).start}, ${getColor(trip).end})`,
                                  left: `${leftPercent}%`,
                                  width: `${Math.max(widthPercent, 2)}%`,
                                }}
                              >
                                <div className="h-full px-3 flex items-center justify-between overflow-visible">
                                  <span className="text-white text-xs font-bold whitespace-nowrap">
                                    {trip.id}
                                  </span>
                                  <span className="text-white/90 text-xs ml-2 whitespace-nowrap">
                                    {formatDuration(durationMinutes)}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>

                        {isSelected && (
                          <div className="bg-blue-900/30 border-t border-blue-700/50 px-4 py-3">
                            <div className="grid grid-cols-4 gap-4 text-sm">
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

        <div className="grid grid-cols-4 gap-4 mt-6">
          <div className="bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg p-4 border border-slate-600">
            <div className="text-slate-400 text-sm mb-2">Total Routes</div>
            <div className="text-4xl font-bold text-blue-400">{filteredTrips.length}</div>
          </div>
          <div className="bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg p-4 border border-slate-600">
            <div className="text-slate-400 text-sm mb-2">Operating Window</div>
            <div className="text-lg font-semibold text-green-400">{calculateOperatingWindow(trips)}</div>
          </div>
          <div className="bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg p-4 border border-slate-600">
            <div className="text-slate-400 text-sm mb-2">Avg Duration</div>
            <div className="text-2xl font-bold text-purple-400">
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
          <div className="bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg p-4 border border-slate-600">
            <div className="text-slate-400 text-sm mb-2">Peak Hour</div>
            <div className="text-lg font-semibold text-orange-400">{calculatePeakHour(trips)}</div>
          </div>
        </div>

            {totalPages > 1 && (
              <div className="flex justify-center items-center mt-6 space-x-2">
                <button
                  onClick={() => handlePageChange(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="px-4 py-2 bg-slate-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-500"
                >
                  Previous
                </button>
                <span className="text-slate-400">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => handlePageChange(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="px-4 py-2 bg-slate-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-500"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}

        {/* Drivers Tab */}
        {activeTab === 'drivers' && (
          <div className="space-y-6">
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg p-4 border border-slate-600">
                <div className="text-slate-400 text-sm mb-2">Total Drivers</div>
                <div className="text-4xl font-bold text-blue-400">{drivers.length}</div>
              </div>
              <div className="bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg p-4 border border-slate-600">
                <div className="text-slate-400 text-sm mb-2">KTEL Buses</div>
                <div className="text-4xl font-bold text-green-400">
                  {drivers.filter(d => d.busAttributes.isKtel === 1).length}
                </div>
              </div>
              <div className="bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg p-4 border border-slate-600">
                <div className="text-slate-400 text-sm mb-2">Avg Cost</div>
                <div className="text-2xl font-bold text-purple-400">
                  {drivers.length > 0
                    ? Math.round(drivers.reduce((acc, d) => acc + d.parameters.cost, 0) / drivers.length)
                    : 0}
                </div>
              </div>
              <div className="bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg p-4 border border-slate-600">
                <div className="text-slate-400 text-sm mb-2">Bus Types</div>
                <div className="text-2xl font-bold text-orange-400">
                  {new Set(drivers.map(d => d.busAttributes.type)).size}
                </div>
              </div>
            </div>

            <div className="bg-slate-800 rounded-xl shadow-2xl overflow-hidden border border-slate-700">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gradient-to-r from-slate-900 to-slate-800 border-b border-slate-700">
                    <tr>
                      <th className="px-4 py-4 text-left text-slate-400 text-sm font-semibold">Driver ID</th>
                      <th className="px-4 py-4 text-left text-slate-400 text-sm font-semibold">Bus ID</th>
                      <th className="px-4 py-4 text-left text-slate-400 text-sm font-semibold">Home Station</th>
                      <th className="px-4 py-4 text-left text-slate-400 text-sm font-semibold">Bus Type</th>
                      <th className="px-4 py-4 text-left text-slate-400 text-sm font-semibold">KTEL</th>
                      <th className="px-4 py-4 text-left text-slate-400 text-sm font-semibold">Cost</th>
                      <th className="px-4 py-4 text-left text-slate-400 text-sm font-semibold">Breaks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {drivers
                      .slice((driverPage - 1) * driversPerPage, driverPage * driversPerPage)
                      .map((driver, idx) => (
                        <tr
                          key={idx}
                          className="border-b border-slate-700 hover:bg-slate-700/50 transition"
                        >
                          <td className="px-4 py-3 text-white font-mono text-sm">{driver.driverId}</td>
                          <td className="px-4 py-3 text-slate-300 font-mono text-sm">{driver.busId}</td>
                          <td className="px-4 py-3 text-slate-300 text-sm">Station {driver.homeStation}</td>
                          <td className="px-4 py-3 text-slate-300 text-sm">
                            <span className="px-2 py-1 bg-blue-600/30 text-blue-300 rounded text-xs">
                              {driver.busAttributes.type}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-slate-300 text-sm">
                            {driver.busAttributes.isKtel === 1 ? (
                              <span className="px-2 py-1 bg-green-600/30 text-green-300 rounded text-xs">Yes</span>
                            ) : (
                              <span className="px-2 py-1 bg-gray-600/30 text-gray-300 rounded text-xs">No</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-slate-300 font-semibold text-sm">{driver.parameters.cost}</td>
                          <td className="px-4 py-3 text-slate-300 text-sm">
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
                  className="px-4 py-2 bg-slate-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-500"
                >
                  Previous
                </button>
                <span className="text-slate-400">
                  Page {driverPage} of {Math.ceil(drivers.length / driversPerPage)}
                </span>
                <button
                  onClick={() => setDriverPage(driverPage + 1)}
                  disabled={driverPage === Math.ceil(drivers.length / driversPerPage)}
                  className="px-4 py-2 bg-slate-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-500"
                >
                  Next
                </button>
              </div>
            )}

            <div className="bg-slate-800 rounded-xl shadow-2xl p-6 border border-slate-700">
              <h3 className="text-xl font-bold text-white mb-4">Bus Type Distribution</h3>
              <div className="space-y-3">
                {Array.from(new Set(drivers.map(d => d.busAttributes.type))).map((type, idx) => {
                  const count = drivers.filter(d => d.busAttributes.type === type).length;
                  const percentage = (count / drivers.length) * 100;
                  return (
                    <div key={idx}>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-slate-300">Type {type}</span>
                        <span className="text-slate-400">{count} drivers ({percentage.toFixed(1)}%)</span>
                      </div>
                      <div className="w-full bg-slate-700 rounded-full h-2">
                        <div
                          className="bg-gradient-to-r from-blue-500 to-purple-500 h-2 rounded-full transition-all"
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="bg-slate-800 rounded-xl shadow-2xl p-6 border border-slate-700">
              <h3 className="text-xl font-bold text-white mb-4">Drivers by Home Station</h3>
              <div className="grid grid-cols-3 gap-4">
                {Array.from(new Set(drivers.map(d => d.homeStation))).sort().map((station, idx) => {
                  const count = drivers.filter(d => d.homeStation === station).length;
                  return (
                    <div key={idx} className="bg-slate-700 rounded-lg p-4">
                      <div className="text-slate-400 text-sm mb-1">Station {station}</div>
                      <div className="text-3xl font-bold text-blue-400">{count}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}