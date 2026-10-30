export interface StationLabel {
  code: string;
  name_el: string;
  name_en?: string;
}
export interface ScheduleDisplayContext {
  stations?: StationLabel[];
  timezone?: string;
  serviceDayStartUtc?: string;
  dayBoundariesMinutes?: number[];
}
export const timeLabel = (minutes: number) =>
  `${String(Math.floor(minutes / 60) % 24).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}${minutes >= 1440 ? ` +${Math.floor(minutes / 1440)}` : ""}`;

export function scheduleDisplay(context: ScheduleDisplayContext = {}) {
  const stations = new Map(
    context.stations?.map((station) => [station.code, station]),
  );
  const boundaries = context.dayBoundariesMinutes ?? [0, 1440, 2880, 4320];
  const start = context.serviceDayStartUtc
    ? Date.parse(context.serviceDayStartUtc)
    : null;
  const clock =
    start !== null && context.timezone
      ? new Intl.DateTimeFormat("en-GB", {
          timeZone: context.timezone,
          hour: "2-digit",
          minute: "2-digit",
          hourCycle: "h23",
        })
      : null;
  const dayIndex = (minutes: number) => {
    const next = boundaries.findIndex((boundary) => boundary > minutes);
    return next < 0 ? boundaries.length - 1 : Math.max(0, next - 1);
  };
  return {
    stationName: (code: string, el: boolean) => {
      const station = stations.get(code);
      return (
        (el
          ? station?.name_el || station?.name_en
          : station?.name_en || station?.name_el) || code
      );
    },
    timeLabel: (minutes: number) => {
      if (start === null || !clock) return timeLabel(minutes);
      const day = dayIndex(minutes);
      return (
        clock.format(new Date(start + minutes * 60000)) +
        (day ? ` +${day}` : "")
      );
    },
    dayIndex,
    dayWindow: (day: number) => ({
      start: boundaries[day] ?? day * 1440,
      end: boundaries[day + 1] ?? (day + 1) * 1440,
    }),
  };
}
