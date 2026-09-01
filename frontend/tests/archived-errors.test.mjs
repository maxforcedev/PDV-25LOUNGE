import assert from "node:assert/strict";
import test from "node:test";

import { archivedRecordConflict } from "../src/lib/archived-errors.ts";

test("parses a branch-scoped archived supplier conflict", () => {
  assert.deepEqual(
    archivedRecordConflict(
      {
        code: "archived_supplier_exists",
        details: {
          supplier_id: 15,
          name: "Fornecedor Histórico",
          archived_at: "2026-08-28T10:00:00Z",
        },
      },
      "archived_supplier_exists",
      "supplier_id",
    ),
    {
      id: 15,
      name: "Fornecedor Histórico",
      archivedAt: "2026-08-28T10:00:00Z",
    },
  );
});

test("rejects a conflict for a different domain code", () => {
  assert.equal(
    archivedRecordConflict(
      {
        code: "archived_category_exists",
        details: {
          category_id: 9,
          name: "Bebidas",
          archived_at: "2026-08-28T10:00:00Z",
        },
      },
      "archived_supplier_exists",
      "supplier_id",
    ),
    null,
  );
});

for (const [code, idField, id, name] of [
  ["archived_user_exists", "user_id", 4, "Rayara"],
  ["archived_category_exists", "category_id", 9, "Bebidas"],
]) {
  test(`parses ${code}`, () => {
    assert.deepEqual(
      archivedRecordConflict(
        {
          code,
          details: {
            [idField]: id,
            name,
            archived_at: "2026-08-28T10:00:00Z",
          },
        },
        code,
        idField,
      ),
      { id, name, archivedAt: "2026-08-28T10:00:00Z" },
    );
  });
}
