// Thin fetch wrapper: same-origin session cookies + Django CSRF token.

export class ApiError extends Error {
  status: number;
  data: Record<string, unknown>;

  constructor(status: number, data: Record<string, unknown>) {
    super(ApiError.messageFrom(data) || `Request failed (${status})`);
    this.status = status;
    this.data = data;
  }

  static messageFrom(data: unknown): string {
    if (!data) return "";
    if (typeof data === "string") return data;
    if (Array.isArray(data)) return data.map(ApiError.messageFrom).join(" ");
    if (typeof data === "object") {
      const d = data as Record<string, unknown>;
      if (d.detail) return ApiError.messageFrom(d.detail);
      if (d.non_field_errors) return ApiError.messageFrom(d.non_field_errors);
      return Object.values(d).map(ApiError.messageFrom).filter(Boolean).join(" ");
    }
    return String(data);
  }

  /** Field-level error, e.g. err.field("email"). */
  field(name: string): string | undefined {
    const v = this.data?.[name];
    return v ? ApiError.messageFrom(v) : undefined;
  }
}

function getCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[2]) : null;
}

let csrfPromise: Promise<void> | null = null;
async function ensureCsrf() {
  if (getCookie("csrftoken")) return;
  csrfPromise ??= fetch("/api/auth/csrf/", { credentials: "same-origin" }).then(() => undefined);
  await csrfPromise;
}

type Body = Record<string, unknown> | unknown[] | FormData | undefined;

export async function request<T = unknown>(method: string, path: string, body?: Body): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const unsafe = !["GET", "HEAD"].includes(method);
  if (unsafe) {
    await ensureCsrf();
    headers["X-CSRFToken"] = getCookie("csrftoken") ?? "";
  }
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, typeof data === "object" ? data : { detail: data || res.statusText });
  return data as T;
}

export const api = {
  get: <T = unknown>(p: string) => request<T>("GET", p),
  post: <T = unknown>(p: string, b?: Body) => request<T>("POST", p, b ?? {}),
  put: <T = unknown>(p: string, b?: Body) => request<T>("PUT", p, b ?? {}),
  patch: <T = unknown>(p: string, b?: Body) => request<T>("PATCH", p, b ?? {}),
  del: <T = unknown>(p: string) => request<T>("DELETE", p),
};

export type Paginated<T> = { count: number; next: string | null; previous: string | null; results: T[] };

/** Build a query string, skipping empty values. */
export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}
