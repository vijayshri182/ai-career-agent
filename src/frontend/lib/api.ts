/**
 * Browser-side API helpers.
 *
 * Data requests go to the same-origin `/api/v1` paths; `middleware.ts`
 * proxies them to the backend and injects the `Authorization: Bearer` header
 * from the HttpOnly cookie, so no token ever touches JavaScript.
 * Auth endpoints (`/api/auth/*`) are Next.js route handlers that manage the
 * cookie server-side.
 */

import type { UserRead } from "./types";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let message = `Request failed with status ${res.status}`;
  try {
    const body = (await res.json()) as unknown;
    if (typeof body === "object" && body !== null) {
      const detail = (body as Record<string, unknown>).detail;
      if (Array.isArray(detail)) {
        message = detail
          .map((d) =>
            typeof d === "object" && d !== null
              ? (d as { msg?: string }).msg
              : String(d),
          )
          .filter(Boolean)
          .join("; ");
      } else if (typeof detail === "string") {
        message = detail;
      }
    }
  } catch {
    // Non-JSON body — keep the generic message.
  }
  return new ApiError(res.status, message);
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    throw await parseError(res);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiDelete(path: string): Promise<void> {
  return request<void>(path, { method: "DELETE" });
}

/** Upload a multipart file (resume). */
export function apiUpload<T>(path: string, body: FormData): Promise<T> {
  return request<T>(path, { method: "POST", body });
}

/* ------------------------------------------------------------------ */
/* auth helpers (client → Next route handler)                          */
/* ------------------------------------------------------------------ */

export async function login(email: string, password: string): Promise<UserRead> {
  return apiPost<UserRead>("/api/auth/login", { email, password });
}

export async function register(
  email: string,
  password: string,
): Promise<UserRead> {
  return apiPost<UserRead>("/api/auth/register", { email, password });
}

export async function logout(): Promise<void> {
  await apiPost<void>("/api/auth/me");
}

export async function getMe(): Promise<UserRead> {
  return apiGet<UserRead>("/api/auth/me");
}