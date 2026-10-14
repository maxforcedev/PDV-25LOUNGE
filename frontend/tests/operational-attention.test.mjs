import assert from "node:assert/strict";
import test from "node:test";

import { operationalAttentionQuery } from "../src/lib/operational-attention.ts";

test("builds repeatable attention filters without a branch query", () => {
  const query = operationalAttentionQuery({
    categories: ["inventory", "printing"], severities: ["critical"], page: 2,
    startDatetime: "2026-10-14T00:00:00-03:00", endDatetime: "2026-10-14T23:59:59-03:00",
  });
  assert.deepEqual(query.getAll("category"), ["inventory", "printing"]);
  assert.deepEqual(query.getAll("severity"), ["critical"]);
  assert.equal(query.get("page"), "2");
  assert.equal(query.get("start_datetime"), "2026-10-14T00:00:00-03:00");
  assert.equal(query.get("end_datetime"), "2026-10-14T23:59:59-03:00");
  assert.equal(query.has("branch"), false);
});
