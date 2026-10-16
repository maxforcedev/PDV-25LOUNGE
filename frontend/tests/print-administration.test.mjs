import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPrintRouteBatch,
  isCurrentPrintAdministrationRequest,
} from "../src/lib/print-administration.ts";

test("rejects late branch administration responses", () => {
  assert.equal(isCurrentPrintAdministrationRequest(3, 3), true);
  assert.equal(isCurrentPrintAdministrationRequest(2, 3), false);
});

test("builds one complete branch route save payload", () => {
  const routes = {
    ticket: { document_type: "ticket", mode: "automatic", printer_device_ids: [7, 9], copies: 2, document_format: "detailed" },
    payment_receipt: { document_type: "payment_receipt", mode: "disabled", printer_device_ids: [], copies: 1, document_format: "simplified" },
  };

  assert.deepEqual(
    buildPrintRouteBatch(["ticket", "payment_receipt"], (type) => routes[type]),
    [
      { document_type: "ticket", mode: "automatic", printer_device_ids: [7, 9], copies: 2, document_format: "detailed" },
      { document_type: "payment_receipt", mode: "disabled", printer_device_ids: [], copies: 1, document_format: "simplified" },
    ],
  );
});
