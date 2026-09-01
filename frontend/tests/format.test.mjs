import assert from "node:assert/strict";
import test from "node:test";

import { centsToDecimal, moneyToCents } from "../src/lib/cash.ts";
import {
  decimalCompare,
  decimalEquals,
  decimalIsOne,
  decimalIsZero,
  formatDecimalBRL,
  formatEditableDecimal,
  formatPercent,
  formatQuantity,
} from "../src/lib/format.ts";

test("formats API decimal quantities without serializer scale", () => {
  assert.equal(formatQuantity("0.000"), "0");
  assert.equal(formatQuantity("5.000"), "5");
  assert.equal(formatQuantity("3.00000000"), "3");
  assert.equal(formatQuantity("1.000"), "1");
  assert.equal(formatQuantity("10.00"), "10");
  assert.equal(formatQuantity("1.250"), "1,25");
});

test("normalizes API decimals for editable inputs", () => {
  assert.equal(formatEditableDecimal("0.000"), "0");
  assert.equal(formatEditableDecimal("5.000"), "5");
  assert.equal(formatEditableDecimal("3.00000000"), "3");
  assert.equal(formatEditableDecimal("1.000"), "1");
  assert.equal(formatEditableDecimal("10.00"), "10");
  assert.equal(formatEditableDecimal("1.250"), "1.25");
});

test("formats percentages without serializer scale", () => {
  assert.equal(formatPercent("10.00"), "10%");
  assert.equal(formatPercent("5.00"), "5%");
  assert.equal(formatPercent("5.500"), "5,5%");
});

test("compares equivalent decimal representations", () => {
  for (const value of ["0", "0.0", "0.00", "0.000", 0]) {
    assert.equal(decimalIsZero(value), true);
  }
  for (const value of ["1", "1.0", "1.00", "1.000", 1]) {
    assert.equal(decimalIsOne(value), true);
  }
  assert.equal(decimalEquals("5", "5.00"), true);
  assert.equal(decimalEquals("5", "5.0"), true);
  assert.equal(decimalEquals("5.00", "5.000"), true);
  assert.equal(decimalEquals("5.0", "5.000"), true);
  assert.equal(decimalEquals("1.25", "1.2500"), true);
  assert.equal(decimalEquals("5", "5.01"), false);
});

test("orders decimal representations without floating point", () => {
  assert.equal(decimalCompare("5.000", "5"), 0);
  assert.equal(decimalCompare("99.999", "100.00"), -1);
  assert.equal(decimalCompare("-10.5", "-10.05"), -1);
  assert.equal(decimalCompare("invalid", "0"), null);
});

test("formats a five-real command change as R$ 5,00", () => {
  const received = moneyToCents("10.00");
  const applied = moneyToCents("5.00");
  assert.notEqual(received, null);
  assert.notEqual(applied, null);
  const change = centsToDecimal(received - applied);
  assert.equal(formatDecimalBRL(change), "R$ 5,00");
});
