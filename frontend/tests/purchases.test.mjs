import assert from "node:assert/strict";
import test from "node:test";

import { formatDecimalBRL } from "../src/lib/format.ts";
import {
  centsText,
  lineTotalCents,
  purchaseBaseUnitPrice,
  purchasePresentationPrice,
} from "../src/lib/purchases.ts";

test("calculates and displays purchase base unit prices", () => {
  assert.equal(purchaseBaseUnitPrice("30", "10"), "3");
  assert.equal(formatDecimalBRL(purchaseBaseUnitPrice("30", "10")), "R$ 3,00");
  assert.equal(purchaseBaseUnitPrice("100", "10"), "10");
  assert.equal(formatDecimalBRL(purchaseBaseUnitPrice("100", "10")), "R$ 10,00");
  assert.equal(formatDecimalBRL("0.234423"), "R$ 0,23");
});

test("synchronizes an edited base price back to presentation price", () => {
  assert.equal(purchasePresentationPrice("3", "10"), "30");
  assert.equal(purchasePresentationPrice("2.50", "12"), "30");
  assert.equal(purchasePresentationPrice("", "12"), "");
  assert.equal(purchaseBaseUnitPrice("", "12"), "");
});

test("keeps purchase subtotal based on presentation price", () => {
  assert.equal(centsText(lineTotalCents("2", "30")), "60.00");
});
