import assert from "node:assert/strict";
import test from "node:test";

import {
  branchPriceState,
  phaseOneReportGroups,
} from "../src/lib/report-presentation.ts";

test("report center exposes only phase one groups and required links", () => {
  assert.deepEqual(phaseOneReportGroups.map((group) => group.title), [
    "Vendas",
    "Financeiro",
    "Estoque",
  ]);
  const reports = phaseOneReportGroups.flatMap((group) => group.reports);
  assert.equal(reports.length, 15);
  assert.equal(reports.find((item) => item.href === "/relatorios/resultado")?.label, "Resultado estimado");
  assert.equal(reports.find((item) => item.href === "/relatorios/descontos")?.label, "Descontos e autorizações");
  assert.equal(reports.find((item) => item.href === "/relatorios/operadores")?.label, "Operadores");
  assert.equal(reports.find((item) => item.href === "/relatorios/movimentacoes")?.permission, "reports.view_inventory");
  assert.equal(reports.some((item) => item.href.includes("fornecedores")), false);
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
