import assert from "node:assert/strict";
import test from "node:test";

import {
  archivedProductConflict,
  uniqueProductErrorMessage,
} from "../src/lib/product-errors.ts";

test("opens the archived product decision for a structured conflict", () => {
  assert.deepEqual(
    archivedProductConflict(
      {
        code: "archived_product_exists",
        message: "Já existiu um produto com este nome.",
        fields: {},
        details: { product_id: 42, name: "Coca", archived_at: "2026-08-28T10:00:00Z" },
      },
      "",
    ),
    { productId: 42, name: "Coca", archivedAt: "2026-08-28T10:00:00Z" },
  );
});

test("does not repeat the same API and field message", () => {
  assert.equal(
    uniqueProductErrorMessage({
      code: null,
      message: "Já existe um produto com este nome nesta empresa.",
      fields: {
        name: ["Já existe um produto com este nome nesta empresa."],
      },
      details: {},
    }),
    "Já existe um produto com este nome nesta empresa.",
  );
});
