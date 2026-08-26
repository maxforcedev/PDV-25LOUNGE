const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000/api/v1"
).replace(/\/$/, "");

let csrfToken: string | null = null;
let csrfRequest: Promise<string> | null = null;
let supportSessionId: string | null = null;

export class ApiError extends Error {
  status: number;
  fields: Record<string, string[]>;
  code: string | null;
  details: Record<string, unknown>;

  constructor(
    message: string,
    status = 0,
    fields: Record<string, string[]> = {},
    code: string | null = null,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
    this.code = code;
    this.details = details;
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
    if (!current || typeof current !== "object" || Array.isArray(current))
      return;
    for (const [key, messages] of Object.entries(current)) {
      if (!prefix && ["detail", "message", "non_field_errors", "code", "details"].includes(key))
        continue;
      const path =
        key === "non_field_errors" && prefix
          ? prefix
          : [prefix, key].filter(Boolean).join(".");
      if (Array.isArray(messages)) {
        const normalized = messages
          .map(safeText)
          .filter((message): message is string => !!message);
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
  if (status >= 500)
    return "Não foi possível concluir a operação devido a um erro interno. Tente novamente.";
  const payload =
    data && typeof data === "object" ? (data as Record<string, unknown>) : {};
  const detail = safeText(payload.detail) || safeText(payload.message);
  if (detail) return detail;
  if (Array.isArray(payload.non_field_errors)) {
    const messages = payload.non_field_errors
      .map(safeText)
      .filter((message): message is string => !!message);
    if (messages.length) return messages.join(" ");
  }
  const fields = normalizeFields(data);
  const fieldMessages = Object.values(fields).flat();
  if (fieldMessages.length) return fieldMessages.join(" ");
  if (status === 400) return "Revise os dados informados e tente novamente.";
  if (status === 401) return "Sua sessão expirou. Entre novamente.";
  if (status === 403) return "Você não tem permissão para realizar esta ação.";
  if (status === 404) return "O item solicitado não foi encontrado.";
  if (status === 409) return "A operação conflita com o estado atual. Atualize e tente novamente.";
  if (status === 429)
    return "Muitas tentativas. Aguarde um momento e tente novamente.";
  return "Não foi possível concluir a solicitação.";
}

export function friendlyError(caught: unknown, fallback: string) {
  if (caught instanceof ApiError) {
    return {
      message: caught.message || fallback,
      fields: caught.fields,
      code: caught.code,
      details: caught.details,
    };
  }
  return { message: fallback, fields: {}, code: null, details: {} };
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
      response = await fetch(`${API_URL}/auth/csrf/`, {
        credentials: "include",
      });
    } catch {
      throw new ApiError("Não foi possível conectar ao servidor.");
    }
    const data = await parseResponse(response);
    if (!response.ok)
      throw new ApiError(
        errorMessage(response.status, data),
        response.status,
        normalizeFields(data),
      );
    const token = (data as { csrf_token?: string } | null)?.csrf_token;
    if (!token)
      throw new ApiError("O servidor não forneceu o token de segurança.");
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
  omitSupportSession?: boolean;
  preserveSupportSessionOnUnauthorized?: boolean;
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

async function request<T>(
  path: string,
  options: RequestOptions = {},
  csrfRetried = false,
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const {
    suppressUnauthorizedEvent,
    omitSupportSession,
    preserveSupportSessionOnUnauthorized,
    ...fetchOptions
  } = options;
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  const headers = new Headers(options.headers);
  const formData =
    typeof FormData !== "undefined" && options.body instanceof FormData;
  if (typeof window !== "undefined") {
    const branchId = window.sessionStorage.getItem("pdv.current_branch_id");
    if (branchId) headers.set("X-Branch-ID", branchId);
    const activeSupportSession =
      supportSessionId ||
      window.sessionStorage.getItem("pdv.support_session_id");
    if (activeSupportSession && !omitSupportSession)
      headers.set("X-Support-Session-ID", activeSupportSession);
  }
  if (unsafe) headers.set("X-CSRFToken", await getCsrfToken());
  if (options.body !== undefined && !formData)
    headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    const url = /^https?:\/\//.test(path)
      ? path
      : `${API_URL}/${path.replace(/^\//, "")}`;
    response = await fetch(url, {
      ...fetchOptions,
      method,
      headers,
      credentials: "include",
      body:
        options.body === undefined
          ? undefined
          : formData
            ? (options.body as FormData)
            : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError("Não foi possível conectar ao servidor.");
  }

  const rotatedToken = response.headers.get("X-CSRFToken");
  if (rotatedToken) csrfToken = rotatedToken;
  const data = await parseResponse(response);
  if (!response.ok) {
    if (
      response.status === 403 &&
      unsafe &&
      !csrfRetried &&
      isCsrfFailure(data)
    ) {
      csrfToken = null;
      await getCsrfToken(true);
      return request<T>(path, options, true);
    }
    if (
      response.status === 401 &&
      headers.has("X-Support-Session-ID") &&
      !preserveSupportSessionOnUnauthorized &&
      typeof window !== "undefined"
    ) {
      clearSupportSessionId();
      window.dispatchEvent(new Event("support:invalid"));
    }
    if (
      response.status === 401 &&
      !suppressUnauthorizedEvent &&
      typeof window !== "undefined"
    )
      window.dispatchEvent(new Event("auth:unauthorized"));
    const payload =
      data && typeof data === "object" ? (data as Record<string, unknown>) : {};
    throw new ApiError(
      errorMessage(response.status, data),
      response.status,
      normalizeFields(data),
      typeof payload.code === "string" ? payload.code : null,
      payload.details && typeof payload.details === "object"
        ? (payload.details as Record<string, unknown>)
        : {},
    );
  }
  return data as T;
}

async function getAll<T>(path: string): Promise<T[]> {
  const results: T[] = [];
  let next: string | null = path;
  while (next) {
    const page: PaginatedResponse<T> =
      await request<PaginatedResponse<T>>(next);
    results.push(...page.results);
    next = page.next;
  }
  return results;
}

async function download(path: string) {
  const headers = new Headers();
  if (typeof window !== "undefined") {
    const branchId = window.sessionStorage.getItem("pdv.current_branch_id");
    if (branchId) headers.set("X-Branch-ID", branchId);
    const activeSupportSession =
      supportSessionId ||
      window.sessionStorage.getItem("pdv.support_session_id");
    if (activeSupportSession)
      headers.set("X-Support-Session-ID", activeSupportSession);
  }
  let response: Response;
  try {
    const url = /^https?:\/\//.test(path)
      ? path
      : `${API_URL}/${path.replace(/^\/?api\/v1\//, "").replace(/^\//, "")}`;
    response = await fetch(url, { credentials: "include", headers });
  } catch {
    throw new ApiError("Não foi possível conectar ao servidor.");
  }
  if (!response.ok) {
    const data = await parseResponse(response);
    throw new ApiError(
      errorMessage(response.status, data),
      response.status,
      normalizeFields(data),
    );
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  return {
    blob: await response.blob(),
    filename: encoded ? decodeURIComponent(encoded) : plain || "anexo",
  };
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  getPublic: <T>(path: string) =>
    request<T>(path, {
      suppressUnauthorizedEvent: true,
      omitSupportSession: true,
    }),
  getAll,
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body }),
  postForm: <T>(path: string, body: FormData) =>
    request<T>(path, { method: "POST", body }),
  postPublic: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body,
      suppressUnauthorizedEvent: true,
      omitSupportSession: true,
    }),
  postWithoutSupport: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body,
      omitSupportSession: true,
      suppressUnauthorizedEvent: true,
    }),
  logout: () =>
    request<void>("auth/logout/", {
      method: "POST",
      suppressUnauthorizedEvent: true,
      preserveSupportSessionOnUnauthorized: true,
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  download,
};

export function clearCsrfToken() {
  csrfToken = null;
}

export function setSupportSessionId(value: number | string) {
  supportSessionId = String(value);
  if (typeof window !== "undefined")
    window.sessionStorage.setItem("pdv.support_session_id", supportSessionId);
}

export function primeSupportSessionId(value: string) {
  supportSessionId = value;
}

export function clearSupportSessionId() {
  supportSessionId = null;
  if (typeof window !== "undefined")
    window.sessionStorage.removeItem("pdv.support_session_id");
}
