"use client";

import { useEffect, useState } from "react";

interface Trip {
  id: string;
  start_station: string;
  end_station: string;
  start_time: string;
  end_time: string;
  start_minutes: number;
  end_minutes: number;
}

export default function HomePage() {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [selectedTrip, setSelectedTrip] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const tripsPerPage = 5;

  useEffect(() => {
    fetch("/api/trips")
      .then((res) => res.json())
      .then((data) => {
        setTrips(data.trips);
      })
      .catch((err) => console.error("Failed to load trips:", err));
  }, []);

  const filteredTrips = trips.filter((trip) => {
    const lowerFilter = searchFilter.toLowerCase();
    const idMatch = trip.id.toLowerCase().includes(lowerFilter);
    const startMatch = trip.start_station.toLowerCase().includes(lowerFilter);
    const endMatch = trip.end_station.toLowerCase().includes(lowerFilter);

    if (lowerFilter.startsWith("stn ")) {
      const station = lowerFilter.slice(4);
      return startMatch || endMatch || trip.start_station.toLowerCase().includes(station) || trip.end_station.toLowerCase().includes(station);
    }

    if (lowerFilter.startsWith("from ")) {
      const station = lowerFilter.slice(5);
      return trip.start_station.toLowerCase().includes(station);
    }

    if (lowerFilter.startsWith("to ")) {
      const station = lowerFilter.slice(3);
      return trip.end_station.toLowerCase().includes(station);
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

  const calculateDuration = (startMinutes: number, endMinutes: number) => {
    if (endMinutes < startMinutes) {
      return endMinutes - startMinutes + 1440; 
    }
    return endMinutes - startMinutes;
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

  const getColor = (tripId: string): string => {
    const colors = [
      "from-blue-500 to-blue-600",
      "from-purple-500 to-purple-600",
      "from-pink-500 to-pink-600",
      "from-green-500 to-green-600",
      "from-yellow-500 to-yellow-600",
      "from-indigo-500 to-indigo-600",
      "from-cyan-500 to-cyan-600",
      "from-red-500 to-red-600",
    ];
    const hash = tripId.split('').reduce((acc, char) => {
        acc = ((acc << 5) - acc) + char.charCodeAt(0);
        return acc & acc;
    }, 0);
    const index = Math.abs(hash) % colors.length;
    return colors[index];
  };

  const calculatePeakHour = (trips: Trip[]): string => {
    if (trips.length === 0) return "N/A";
    const hourCounts: { [key: number]: number } = {};
    trips.forEach((trip) => {
      const hour = Math.floor(trip.start_minutes / 60);
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
    const minStart = Math.min(...trips.map(t => t.start_minutes));
    const maxEnd = Math.max(...trips.map(t => t.end_minutes));
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
                    const durationMinutes = calculateDuration(trip.start_minutes, trip.end_minutes);
                    const leftPercent = timeToPixels(trip.start_minutes);
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
                                <span className="text-slate-500">From:</span> Stn {trip.start_station}
                              </div>
                              <div>
                                <span className="text-slate-500">To:</span> Stn {trip.end_station}
                              </div>
                              <div className="pt-1 mt-1 border-t border-slate-600">
                                <span className="text-slate-300 font-mono">
                                  {trip.start_time} → {trip.end_time}
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
                                className={`absolute top-2 bottom-2 bg-gradient-to-r ${getColor(
                                  trip.id
                                )} rounded-lg shadow-lg transition-all transform hover:scale-y-110 hover:shadow-xl border border-white/20`}
                                style={{
                                  left: `${leftPercent}%`,
                                  width: `${Math.max(widthPercent, 2)}%`,
                                }}
                              >
                                <div className="h-full px-3 flex items-center justify-between overflow-visible">
                                  <span className="text-white text-xs font-bold whitespace-nowrap">
                                    {trip.id}
                                  </span>
                                  <span className="text-white/90 text-xs ml-2 whitespace-nowrap">
                                    {durationMinutes}m ({Math.floor(durationMinutes / 60)}h)
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
                                  {durationMinutes} minutes
                                </div>
                              </div>
                              <div>
                                <span className="text-slate-400">Departure</span>
                                <div className="text-blue-300 font-semibold">
                                  {trip.start_time}
                                </div>
                              </div>
                              <div>
                                <span className="text-slate-400">Arrival</span>
                                <div className="text-blue-300 font-semibold">
                                  {trip.end_time}
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
                ? Math.round(
                    filteredTrips.reduce(
                      (acc, t) => acc + calculateDuration(t.start_minutes, t.end_minutes),
                      0
                    ) / filteredTrips.length
                  )
                : 0}
              m
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
      </div>
    </main>
  );
}