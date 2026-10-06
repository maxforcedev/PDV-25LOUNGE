import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import { resolveLegalTemplate } from "../src/lib/legal-documents.ts";

const branding = {
  platform_name: "CORE PDV", support_email: "suporte@example.com", support_phone: "11999999999",
  legal_settings: { legal_name: "Empresa Exemplo", cnpj: "69.366.055/0001-16", privacy_email: "privacidade@example.com", dpo_email: "dpo@example.com", effective_date: "2026-10-05" },
};

test("resolves centralized values and leaves contracting-party data untouched", () => {
  const { markdown, missing } = resolveLegalTemplate("{{legal_name}} / {{cnpj}} / {{support_contact}} / {{effective_date}} / [REGISTRADO PELO CONTRATANTE]", branding);
  assert.match(markdown, /Empresa Exemplo/);
  assert.match(markdown, /suporte@example.com \/ 11999999999/);
  assert.match(markdown, /5 de outubro de 2026/);
  assert.match(markdown, /\[REGISTRADO PELO CONTRATANTE\]/);
  assert.deepEqual(missing, []);
});

test("reports missing data without inventing company contacts", () => {
  const result = resolveLegalTemplate("{{address}} {{address}} {{legal_email}}", branding);
  assert.deepEqual(result.missing, ["endereço", "e-mail jurídico"]);
  assert.match(result.markdown, /endereço: não informado/);
  assert.doesNotMatch(result.markdown, /suporte@example.com/);
});

test("all legal pages resolve tokens and preserve numbered sections and annexes", () => {
  for (const slug of ["termos-de-uso", "privacidade", "licenca-e-assinatura", "tratamento-de-dados"]) {
    const document = JSON.parse(fs.readFileSync(new URL(`../src/content/legal/${slug}.json`, import.meta.url), "utf8"));
    const result = resolveLegalTemplate(document.markdown, branding);
    assert.doesNotMatch(result.markdown, /\{\{[a-z_]+\}\}/);
    assert.match(result.markdown, /Versão.*1\.0/);
    assert.match(result.markdown, /# 1\./);
    assert.ok(document.sha256.length === 64);
    if (slug === "tratamento-de-dados") assert.match(result.markdown, /ANEXO IV/);
  }
});
