import assert from "node:assert/strict";
import test from "node:test";

import { applyModifierProductSuggestion } from "../src/lib/modifier-option-suggestions.ts";

const emptyForm = {
  name: "",
  additional_price: "0",
  stock_product: "",
};

test("suggests the selected product name and effective branch price", () => {
  assert.deepEqual(
    applyModifierProductSuggestion(emptyForm, {
      id: 12,
      name: "Coca-Cola Lata",
      sale_price: "7.00",
      effective_sale_price: "8.00",
    }, { name: false, additionalPrice: false }),
    { name: "Coca-Cola Lata", additional_price: "8.00", stock_product: "12" },
  );
});

test("falls back to the product default price and preserves manual fields", () => {
  const edited = applyModifierProductSuggestion({
    name: "Nome personalizado",
    additional_price: "9.50",
    stock_product: "12",
  }, {
    id: 13,
    name: "Outro produto",
    sale_price: "6.00",
  }, { name: true, additionalPrice: true });

  assert.deepEqual(edited, {
    name: "Nome personalizado",
    additional_price: "9.50",
    stock_product: "13",
  });
});
