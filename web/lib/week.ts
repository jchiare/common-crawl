// Weeks are identified by the ISO date (YYYY-MM-DD) of their Monday.
// All maths is done in UTC on plain dates so it never shifts with the server's zone.

const DAY_MS = 86_400_000;

function parse(date: string): Date {
  return new Date(`${date}T00:00:00Z`);
}

function format(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(parse(value).getTime());
}

export function addDays(date: string, days: number): string {
  return format(new Date(parse(date).getTime() + days * DAY_MS));
}

/** Monday of the week containing `date`. */
export function mondayOf(date: string): string {
  const d = parse(date);
  const sinceMonday = (d.getUTCDay() + 6) % 7;
  return addDays(date, -sinceMonday);
}

export function isMonday(date: string): boolean {
  return isIsoDate(date) && parse(date).getUTCDay() === 1;
}

/** Today's date in the clinic's timezone (CLINIC_TIMEZONE, default UTC). */
export function today(): string {
  const timeZone = process.env.CLINIC_TIMEZONE || "UTC";
  // en-CA formats as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", { timeZone }).format(new Date());
}

export function currentWeek(): string {
  return mondayOf(today());
}

export function weekDays(weekStart: string): string[] {
  return Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
}

export function formatWeek(weekStart: string): string {
  const fmt = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", timeZone: "UTC" });
  return `${fmt.format(parse(weekStart))} – ${fmt.format(parse(addDays(weekStart, 6)))}`;
}

export function formatDay(date: string): string {
  return new Intl.DateTimeFormat("en", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(parse(date));
}

export function weekdayLetter(date: string): string {
  return new Intl.DateTimeFormat("en", { weekday: "narrow", timeZone: "UTC" }).format(parse(date));
}
