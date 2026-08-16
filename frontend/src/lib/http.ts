const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000/api/v1").replace(/\/$/, "");

let csrfToken: string | null = null;
let csrfRequest: Promise<string> | null = null;

export class ApiError extends Error {
  status: number;
  fields: Record<string, string[]>;

  constructor(message: string, status = 0, fields: Record<string, string[]> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
  }
}

function safeText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  return text && !/<\/?[a-z][\s\S]*>/i.test(text) ? text : null;
}

function normalizeFields(value: unknown): Record<string, string[]> {
  const fields: Record<string, string[]> = {};

  function visit(current: unknown, prefix = "") {
    if (!current || typeof current !== "object" || Array.isArray(current)) return;
    for (const [key, messages] of Object.entries(current)) {
      if (!prefix && ["detail", "message", "non_field_errors"].includes(key)) continue;
      const path = key === "non_field_errors" && prefix ? prefix : [prefix, key].filter(Boolean).join(".");
      if (Array.isArray(messages)) {
        const normalized = messages.map(safeText).filter((message): message is string => !!message);
        if (normalized.length) fields[path] = normalized;
        messages.forEach((message) => visit(message, path));
      } else if (typeof messages === "string") {
        const message = safeText(messages);
        if (message) fields[path] = [message];
      } else {
        visit(messages, path);
      }
    }
  }

  visit(value);
  return fields;
}

function errorMessage(status: number, data: unknown): string {
  if (status >= 500) return "O servidor encontrou um problema. Tente novamente em instantes.";
  const payload = data && typeof data === "object" ? (data as Record<string, unknown>) : {};
  const detail = safeText(payload.detail) || safeText(payload.message);
  if (detail) return detail;
  if (Array.isArray(payload.non_field_errors)) {
    const messages = payload.non_field_errors.map(safeText).filter((message): message is string => !!message);
    if (messages.length) return messages.join(" ");
  }
  if (status === 401) return "Sua sessão expirou. Entre novamente.";
  if (status === 403) return "Você não tem permissão para realizar esta ação.";
  if (status === 429) return "Muitas tentativas. Aguarde um momento e tente novamente.";
  return "Não foi possível concluir a solicitação.";
}

async function parseResponse(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }
  const text = await response.text();
  const detail = safeText(text);
  return detail ? { detail } : null;
}

export async function getCsrfToken(force = false): Promise<string> {
  if (csrfToken && !force) return csrfToken;
  if (csrfRequest && !force) return csrfRequest;
  csrfRequest = (async () => {
    let response: Response;
    try {
      response = await fetch(`${API_URL}/auth/csrf/`, { credentials: "include" });
    } catch {
      throw new ApiError("Não foi possível conectar ao servidor.");
    }
    const data = await parseResponse(response);
    if (!response.ok) throw new ApiError(errorMessage(response.status, data), response.status, normalizeFields(data));
    const token = (data as { csrf_token?: string } | null)?.csrf_token;
    if (!token) throw new ApiError("O servidor não forneceu o token de segurança.");
    csrfToken = token;
    return token;
  })().finally(() => {
    csrfRequest = null;
  });
  return csrfRequest;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  suppressUnauthorizedEvent?: boolean;
}

interface PaginatedResponse<T> {
  next: string | null;
  results: T[];
}

function isCsrfFailure(data: unknown) {
  if (typeof data === "string") return /csrf/i.test(data);
  if (!data || typeof data !== "object") return false;
  const detail = (data as Record<string, unknown>).detail;
  return typeof detail === "string" && /csrf/i.test(detail);
}

async function request<T>(path: string, options: RequestOptions = {}, csrfRetried = false): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const { suppressUnauthorizedEvent, ...fetchOptions } = options;
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  const headers = new Headers(options.headers);
  if (typeof window !== "undefined") {
    const branchId = window.sessionStorage.getItem("pdv.current_branch_id");
    if (branchId) headers.set("X-Branch-ID", branchId);
  }
  if (unsafe) headers.set("X-CSRFToken", await getCsrfToken());
  if (options.body !== undefined) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    const url = /^https?:\/\//.test(path) ? path : `${API_URL}/${path.replace(/^\//, "")}`;
    response = await fetch(url, {
      ...fetchOptions,
      method,
      headers,
      credentials: "include",
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError("Não foi possível conectar ao servidor.");
  }

  const rotatedToken = response.headers.get("X-CSRFToken");
  if (rotatedToken) csrfToken = rotatedToken;
  const data = await parseResponse(response);
  if (!response.ok) {
    if (response.status === 403 && unsafe && !csrfRetried && isCsrfFailure(data)) {
      csrfToken = null;
      await getCsrfToken(true);
      return request<T>(path, options, true);
    }
    if (response.status === 401 && !suppressUnauthorizedEvent && typeof window !== "undefined") window.dispatchEvent(new Event("auth:unauthorized"));
    throw new ApiError(errorMessage(response.status, data), response.status, normalizeFields(data));
  }
  return data as T;
}

async function getAll<T>(path: string): Promise<T[]> {
  const results: T[] = [];
  let next: string | null = path;
  while (next) {
    const page: PaginatedResponse<T> = await request<PaginatedResponse<T>>(next);
    results.push(...page.results);
    next = page.next;
  }
  return results;
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  getAll,
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  logout: () => request<void>("auth/logout/", { method: "POST", suppressUnauthorizedEvent: true }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body }),
};

export function clearCsrfToken() {
  csrfToken = null;
}
