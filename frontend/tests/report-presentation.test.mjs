import assert from "node:assert/strict";
import test from "node:test";

import {
  branchPriceState,
  reportGroups,
} from "../src/lib/report-presentation.ts";

test("report center exposes current feature-gated groups and required links", () => {
  assert.deepEqual(reportGroups.map((group) => group.title), [
    "Vendas",
    "Financeiro",
    "Estoque",
    "Inventários",
    "Compras",
    "Operação",
  ]);
  const reports = reportGroups.flatMap((group) => group.reports);
  assert.equal(reports.length, 26);
  assert.equal(reports.find((item) => item.href === "/relatorios/resultado")?.label, "Resultado estimado");
  assert.equal(reports.find((item) => item.href === "/relatorios/descontos")?.label, "Descontos e autorizações");
  assert.equal(reports.find((item) => item.href === "/relatorios/operadores")?.label, "Operadores");
  assert.equal(reports.find((item) => item.href === "/relatorios/movimentacoes")?.permission, "reports.view_inventory");
  assert.equal(reports.find((item) => item.href === "/relatorios/fornecedores")?.permission, "suppliers.view");
});

test("unavailable branch price takes precedence over specific and inherited prices", () => {
  assert.deepEqual(branchPriceState(false, "12.00", "10.00"), {
    kind: "unavailable",
    price: null,
    detail: "Não disponível",
  });
  assert.deepEqual(branchPriceState(true, "12.00", "10.00"), {
    kind: "specific",
    price: "12.00",
    detail: "Preço da filial",
  });
  assert.deepEqual(branchPriceState(true, null, "10.00"), {
    kind: "inherited",
    price: "10.00",
    detail: "Preço padrão",
  });
});
