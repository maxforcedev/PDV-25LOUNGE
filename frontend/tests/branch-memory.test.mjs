import assert from "node:assert/strict";
import test from "node:test";

import {
  parseBranchMemory,
  selectActiveBranch,
  serializeBranchMemory,
  withRememberedBranch,
} from "../src/lib/branch-memory.ts";

const branches = [
  { id: 10, company_id: 1, status: "active" },
  { id: 11, company_id: 1, status: "inactive" },
  { id: 20, company_id: 2, status: "active" },
];

test("round-trips versioned per-company branch memory", () => {
  const memory = withRememberedBranch({ "1": 10 }, 2, 20);

  assert.deepEqual(parseBranchMemory(serializeBranchMemory(memory)), {
    "1": 10,
    "2": 20,
  });
});

test("treats malformed, unknown-version, and invalid entries as unusable", () => {
  assert.deepEqual(parseBranchMemory("not json"), {});
  assert.deepEqual(
    parseBranchMemory('{"version":2,"branches":{"1":10}}'),
    {},
  );
  assert.deepEqual(
    parseBranchMemory(
      '{"version":1,"branches":{"1":10,"2":"20","bad":30,"3":-1}}',
    ),
    { "1": 10 },
  );
});

test("selects a remembered branch only when accessible, active, and in company", () => {
  assert.equal(selectActiveBranch(branches, 1, true, 10)?.id, 10);
  assert.equal(selectActiveBranch(branches, 1, true, 11)?.id, 10);
  assert.equal(selectActiveBranch(branches, 1, true, 20)?.id, 10);
  assert.equal(selectActiveBranch(branches, 1, false, 10), undefined);
});

test("uses a valid compatibility branch before the first active fallback", () => {
  const choices = [
    { id: 10, company_id: 1, status: "active" },
    { id: 12, company_id: 1, status: "active" },
  ];

  assert.equal(selectActiveBranch(choices, 1, true, 999, 12)?.id, 12);
  assert.equal(selectActiveBranch(choices, 1, true, 999, 999)?.id, 10);
});
