import assert from "node:assert/strict";
import test from "node:test";

import {
  dashboardPeriods,
  dashboardQuery,
  validDashboardPeriod,
} from "../src/lib/period.ts";

test("builds today, 7-day and 30-day dashboard periods", () => {
  const periods = dashboardPeriods(new Date("2026-09-01T15:00:00Z"));
  assert.deepEqual(
    periods.map(([label]) => label),
    ["Hoje", "7 dias", "30 dias"],
  );
  assert.equal(periods[0][1].start, "2026-09-01T00:00:00");
  assert.equal(periods[1][1].start, "2026-08-26T00:00:00");
  assert.equal(periods[2][1].start, "2026-08-03T00:00:00");
});

test("accepts only a complete ordered custom period", () => {
  assert.equal(
    validDashboardPeriod({
      start: "2026-08-10T08:00:00",
      end: "2026-08-12T18:00:00",
    }),
    true,
  );
  assert.equal(
    validDashboardPeriod({
      start: "2026-08-12T18:00:00",
      end: "2026-08-10T08:00:00",
    }),
    false,
  );
});

test("dashboard query uses the global branch context instead of duplicating it", () => {
  const query = dashboardQuery({
    start: "2026-09-01T00:00:00",
    end: "2026-09-01T23:59:59",
  });
  assert.equal(query.has("branch"), false);
  assert.equal(query.get("latest_sales_page"), "1");
});
