export const BUSINESS_TIME_ZONE = "America/Sao_Paulo";

export interface PeriodValue {
  start: string;
  end: string;
}

export interface BusinessHour {
  date: string;
  hour: number;
  label: string;
  detailLabel: string;
  start: string;
  end: string;
}

export type PeriodPreset =
  | "today"
  | "yesterday"
  | "week"
  | "fortnight"
  | "month";

const businessDateFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: BUSINESS_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const businessDateTimeFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: BUSINESS_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

function parts(formatter: Intl.DateTimeFormat, value: Date) {
  return Object.fromEntries(
    formatter
      .formatToParts(value)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
}

function businessDate(value: Date) {
  const date = parts(businessDateFormatter, value);
  return `${date.year}-${date.month}-${date.day}`;
}

function shiftDate(date: string, days: number) {
  const [year, month, day] = date.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}-${String(shifted.getUTCDate()).padStart(2, "0")}`;
}

export function businessPeriod(
  days = 0,
  offset = 0,
  now = new Date(),
): PeriodValue {
  const endDate = shiftDate(businessDate(now), offset);
  const startDate = shiftDate(endDate, -days);
  return {
    start: `${startDate}T00:00:00`,
    end: `${endDate}T23:59:59`,
  };
}

export function businessPeriodPreset(
  preset: PeriodPreset,
  now = new Date(),
): PeriodValue {
  if (preset === "yesterday") return businessPeriod(0, -1, now);
  if (preset === "week") return businessPeriod(6, 0, now);
  if (preset === "fortnight") return businessPeriod(14, 0, now);
  if (preset === "month") return businessPeriod(29, 0, now);
  return businessPeriod(0, 0, now);
}

export function dashboardPeriods(now = new Date()) {
  return [
    ["Hoje", businessPeriod(0, 0, now)],
    ["7 dias", businessPeriod(6, 0, now)],
    ["30 dias", businessPeriod(29, 0, now)],
  ] as const;
}

export function dashboardAnalysisPeriods(now = new Date()) {
  return [
    ["Hoje", businessPeriod(0, 0, now)],
    ["Ontem", businessPeriod(0, -1, now)],
    ["7 dias", businessPeriod(6, 0, now)],
    ["30 dias", businessPeriod(29, 0, now)],
    ["Este mês", businessMonthToDate(now)],
  ] as const;
}

export function validDashboardPeriod(period: PeriodValue) {
  return Boolean(period.start && period.end && period.start <= period.end);
}

export function dashboardQuery(period: PeriodValue) {
  return new URLSearchParams({
    start_datetime: period.start,
    end_datetime: period.end,
    latest_sales_page: "1",
  });
}

export function businessMonthToDate(now = new Date()): PeriodValue {
  const endDate = businessDate(now);
  return {
    start: `${endDate.slice(0, 7)}-01T00:00:00`,
    end: `${endDate}T23:59:59`,
  };
}

export function toBusinessDateTimeLocal(value: string | Date) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const dateTime = parts(businessDateTimeFormatter, date);
  return `${dateTime.year}-${dateTime.month}-${dateTime.day}T${dateTime.hour}:${dateTime.minute}:${dateTime.second}`;
}

function validBusinessDate(value?: string) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
    ? value
    : undefined;
}

/** Normalizes API hour buckets to the operation's commercial timezone. */
export function businessHour(value: string, fallbackDate?: string): BusinessHour | undefined {
  const raw = value.trim();
  let local = "";
  if (/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)) local = toBusinessDateTimeLocal(raw);
  else if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(raw)) local = raw.slice(0, 19);

  const dateTime = local.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}):\d{2}(?::\d{2})?$/);
  const time = raw.match(/^(\d{1,2})(?::\d{2}(?::\d{2})?)?$/);
  const date = validBusinessDate(dateTime?.[1] || fallbackDate);
  const hour = Number(dateTime?.[2] || time?.[1]);
  if (!date || !Number.isInteger(hour) || hour < 0 || hour > 23) return undefined;

  const hourLabel = `${String(hour).padStart(2, "0")}h`;
  return {
    date,
    hour,
    label: hourLabel,
    detailLabel: `${date.slice(8, 10)}/${date.slice(5, 7)} — ${hourLabel}`,
    start: `${date}T${String(hour).padStart(2, "0")}:00:00`,
    end: `${date}T${String(hour).padStart(2, "0")}:59:59`,
  };
}
