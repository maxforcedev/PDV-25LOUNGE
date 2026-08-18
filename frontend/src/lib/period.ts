export const BUSINESS_TIME_ZONE = "America/Sao_Paulo";

export interface PeriodValue {
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
