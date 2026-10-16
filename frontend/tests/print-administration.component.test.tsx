import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import React from "react";
import type { AuthContextValue } from "../src/providers/auth-provider";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost" });
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  Event: dom.window.Event,
  MouseEvent: dom.window.MouseEvent,
});
Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function components() {
  const testing = await import("@testing-library/react");
  const routes = await import("../src/components/document-print-routes");
  const management = await import("../src/components/printer-management");
  const authProvider = await import("../src/providers/auth-provider");
  return { ...testing, ...routes, ...management, ...authProvider };
}

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };
function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  return { promise: new Promise<T>((done) => { resolve = done; }), resolve };
}

function json(value: unknown) {
  return new Response(JSON.stringify(value), { headers: { "content-type": "application/json" } });
}

const branch = { id: 1, name: "Filial A", permissions: ["printers.manage", "print_routes.manage", "print_jobs.view"], company_id: 1 };
const auth = {
  currentBranch: branch,
  currentCompany: { id: 1 },
  supportSession: null,
  user: { is_superuser: false, branches: [branch] },
};

function withAuth(Context: React.Context<AuthContextValue | null>, node: React.ReactNode) {
  return React.createElement(Context.Provider, { value: auth as AuthContextValue }, node);
}

test("route refresh cannot replace a draft when its delayed response arrives", async () => {
  const { DocumentPrintRoutes, AuthContext, fireEvent, render, screen, waitFor } = await components();
  const initialRoutes = deferred<Response>();
  const initialCatalog = deferred<Response>();
  const refreshRoutes = deferred<Response>();
  const refreshCatalog = deferred<Response>();
  let routeCalls = 0;
  let catalogCalls = 0;
  globalThis.fetch = (input: URL | RequestInfo) => {
    const url = String(input);
    if (url.includes("print-routes/")) return Promise.resolve(++routeCalls === 1 ? initialRoutes.promise : refreshRoutes.promise);
    if (url.includes("route-options/")) return Promise.resolve(++catalogCalls === 1 ? initialCatalog.promise : refreshCatalog.promise);
    throw new Error(`Unexpected request ${url}`);
  };

  const rendered = render(withAuth(AuthContext, <DocumentPrintRoutes branchId={1} branchName="Filial A" />));
  initialRoutes.resolve(json({ results: [{ id: 1, branch: 1, document_type: "ticket", mode: "disabled", printer_device_ids: [], copies: 1, document_format: "detailed", created_at: "", updated_at: "" }], next: null }));
  initialCatalog.resolve(json({ results: [{ id: 7, name: "Cozinha", status: "active", connection_type: "network" }], next: null }));
  await screen.findByText("Ticket");
  await waitFor(() => assert.ok(rendered.container.querySelector("select")));

  fireEvent.click(screen.getByRole("button", { name: "Atualizar" }));
  await waitFor(() => assert.equal(routeCalls, 2));
  fireEvent.change(rendered.container.querySelector("select")!, { target: { value: "automatic" } });
  refreshRoutes.resolve(json({ results: [{ id: 1, branch: 1, document_type: "ticket", mode: "disabled", printer_device_ids: [], copies: 1, document_format: "detailed", created_at: "", updated_at: "" }], next: null }));
  refreshCatalog.resolve(json({ results: [], next: null }));

  await waitFor(() => assert.match(screen.getByText("Há alterações de rotas não salvas.").textContent || "", /alterações/));
  assert.equal((rendered.container.querySelector("select") as HTMLSelectElement).value, "automatic");
  rendered.unmount();
});

test("equipment and history retain independent delayed loads", async () => {
  const { PrinterManagement, AuthContext, fireEvent, render, screen } = await components();
  const equipment = deferred<Response>();
  const destinations = deferred<Response>();
  const history = deferred<Response>();
  globalThis.fetch = (input: URL | RequestInfo) => {
    const url = String(input);
    if (url.includes("printer-devices/")) return equipment.promise;
    if (url.includes("production-destinations/")) return destinations.promise;
    if (url.includes("print-jobs/")) return history.promise;
    throw new Error(`Unexpected request ${url}`);
  };

  const rendered = render(withAuth(AuthContext, <PrinterManagement branchId={1} branchName="Filial A" branchPermissions={branch.permissions} />));
  fireEvent.click(screen.getByRole("tab", { name: "Histórico" }));
  history.resolve(json({ results: [{ id: 4, origin_label: "Teste de impressão", created_at: "2026-01-01T00:00:00Z", printer_name: "Cozinha", status: "printed", attempts: 1, reprint_eligible: false }], next: null, count: 1 }));
  destinations.resolve(json({ results: [], next: null }));
  equipment.resolve(json({ results: [{ id: 7, name: "Cozinha", connection_type: "network", status: "active", destination_ids: [], technical_configuration: {}, connection_summary: "", operational_status: "not_tested", last_seen_at: null, last_test_at: null, last_operational_error: "", created_at: "", updated_at: "", branch: 1, device_type: "manual" }], next: null }));
  await screen.findByText("Teste de impressão");
  fireEvent.click(screen.getByRole("tab", { name: "Equipamentos" }));
  await screen.findByText("Cozinha");
  rendered.unmount();
});
