import assert from "node:assert/strict";
import test from "node:test";

import {
  productBranchConfigPayload,
  visibleProductBranchChannels,
} from "../src/lib/product-branch-channels.ts";

const configuration = {
  is_available: true,
  available_counter: false,
  available_table: true,
  available_command: false,
  participates_in_service_fee: null,
  participates_in_commission: true,
};

test("shows only the channels enabled for the branch", () => {
  assert.deepEqual(
    visibleProductBranchChannels({ counter: true, tables: false, commands: true }),
    ["counter", "command"],
  );
});

test("does not submit channels hidden by branch features", () => {
  assert.deepEqual(
    productBranchConfigPayload(configuration, {
      counter: true,
      tables: false,
      commands: true,
    }),
    {
      is_available: true,
      available_counter: false,
      available_command: false,
      participates_in_service_fee: null,
      participates_in_commission: true,
    },
  );
});
