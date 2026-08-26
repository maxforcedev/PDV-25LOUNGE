const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

let csrfToken: string | null = null;
let csrfRequest: Promise<string> | null = null;

interface Page<T> {
  results: T[];
  next: string | null;
}

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

function safeText(value: unknown) {
  return typeof value === "string" && !/<\/?[a-z][\s\S]*>/i.test(value) ? value.trim() : "";
}

function fieldsFrom(data: unknown) {
  const fields: Record<string, string[]> = {};
  if (!data || typeof data !== "object" || Array.isArray(data)) return fields;
  for (const [key, value] of Object.entries(data)) {
    if (["detail", "message", "non_field_errors"].includes(key)) continue;
    const values = Array.isArray(value) ? value : [value];
    const messages = values.map(safeText).filter(Boolean);
    if (messages.length) fields[key] = messages;
  }
  return fields;
}

function messageFrom(status: number, data: unknown) {
  const payload = data && typeof data === "object" ? data as Record<string, unknown> : {};
  const detail = safeText(payload.detail) || safeText(payload.message);
  if (detail) return detail;
  if (Array.isArray(payload.non_field_errors)) {
    const messages = payload.non_field_errors.map(safeText).filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  const fieldMessages = Object.values(fieldsFrom(data)).flat();
  if (fieldMessages.length) return fieldMessages.join(" ");
  if (status === 401) return "Sua sessao expirou. Entre novamente.";
  if (status === 403) return "Permissao insuficiente para esta operacao.";
  if (status === 429) return "Limite de tentativas atingido. Aguarde e tente novamente.";
  if (status >= 500) return "O servidor encontrou um problema. Tente novamente.";
  return "Nao foi possivel concluir a solicitacao.";
}

async function parse(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  if ((response.headers.get("content-type") || "").includes("application/json")) {
    try { return await response.json(); } catch { return null; }
  }
  const text = safeText(await response.text());
  return text ? { detail: text } : null;
}

export async function getCsrf(force = false) {
  if (!API_URL) throw new ApiError("NEXT_PUBLIC_API_URL nao configurada.");
  if (csrfToken && !force) return csrfToken;
  if (csrfRequest && !force) return csrfRequest;
  csrfRequest = (async () => {
    let response: Response;
    try {
      response = await fetch(`${API_URL}/auth/csrf/`, { credentials: "include" });
    } catch {
      throw new ApiError("Nao foi possivel conectar ao servidor.");
    }
    const data = await parse(response);
    if (!response.ok) throw new ApiError(messageFrom(response.status, data), response.status, fieldsFrom(data));
    const token = (data as { csrf_token?: string } | null)?.csrf_token;
    if (!token) throw new ApiError("Token de seguranca nao recebido.");
    csrfToken = token;
    return token;
  })().finally(() => { csrfRequest = null; });
  return csrfRequest;
}

interface Options extends Omit<RequestInit, "body"> { body?: unknown; silent401?: boolean }

async function request<T>(path: string, options: Options = {}, retried = false): Promise<T> {
  if (!API_URL && !/^https?:\/\//.test(path)) throw new ApiError("NEXT_PUBLIC_API_URL nao configurada.");
  const method = (options.method || "GET").toUpperCase();
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  const headers = new Headers(options.headers);
  if (unsafe) headers.set("X-CSRFToken", await getCsrf());
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    const url = /^https?:\/\//.test(path) ? path : `${API_URL}/${path.replace(/^\//, "")}`;
    response = await fetch(url, {
      ...options,
      method,
      headers,
      credentials: "include",
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError("Nao foi possivel conectar ao servidor.");
  }
  const rotated = response.headers.get("X-CSRFToken");
  if (rotated) csrfToken = rotated;
  const data = await parse(response);
  if (!response.ok) {
    const detail = data && typeof data === "object" ? safeText((data as Record<string, unknown>).detail) : "";
    if (response.status === 403 && unsafe && !retried && /csrf/i.test(detail)) {
      csrfToken = null;
      await getCsrf(true);
      return request<T>(path, options, true);
    }
    if (response.status === 401 && !options.silent401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event("platform:unauthorized"));
    }
    throw new ApiError(messageFrom(response.status, data), response.status, fieldsFrom(data));
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  list: async <T>(path: string) => {
    const rows: T[] = [];
    let next: string | null = path;
    while (next !== null) {
      const currentUrl: string = next;
      const page: T[] | Page<T> = await request<T[] | Page<T>>(currentUrl);
      if (Array.isArray(page)) { rows.push(...page); next = null; }
      else { rows.push(...page.results); next = page.next; }
    }
    return rows;
  },
  post: <T>(path: string, body?: unknown, silent401 = false) => request<T>(path, { method: "POST", body, silent401 }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body }),
};

export function clearCsrf() { csrfToken = null; }
