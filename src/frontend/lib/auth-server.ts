/**
 * Server-only auth helpers used by the `/api/auth/*` route handlers.
 * Never import this module from client components.
 */

import "server-only";

import { NextResponse } from "next/server";

import { API_BASE } from "./config";

export const AUTH_COOKIE = "access_token";

interface BackendResult<T> {
  status: number;
  body: T;
}

async function backendRequest<T>(
  path: string,
  token: string | undefined,
  init?: RequestInit,
): Promise<BackendResult<T>> {
  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (res.status === 204) {
    return { status: 204, body: undefined as T };
  }
  const text = await res.text();
  let body: T;
  try {
    body = (text ? JSON.parse(text) : null) as T;
  } catch {
    body = { detail: text } as T;
  }
  return { status: res.status, body };
}

export function setSessionToken(
  res: NextResponse,
  token: string,
): NextResponse {
  res.cookies.set(AUTH_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });
  return res;
}

export function clearSessionToken(res: NextResponse): NextResponse {
  res.cookies.set(AUTH_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return res;
}

/** Exchange credentials for a session cookie backed by the backend token. */
export async function createSession(
  path: "/auth/login" | "/auth/register",
  body: unknown,
): Promise<NextResponse> {
  const { status, body: result } = await backendRequest<{
    access_token?: string;
    detail?: unknown;
  }>(path, undefined, { method: "POST", body: JSON.stringify(body) });

  if (status !== 200 && status !== 201) {
    return NextResponse.json(
      { detail: extractDetail(result) },
      { status },
    );
  }

  const token = result.access_token;
  if (!token) {
    return NextResponse.json(
      { detail: "Backend returned no access token" },
      { status: 502 },
    );
  }

  const me = await backendRequest<Record<string, unknown> | { detail: unknown }>(
    "/auth/me",
    token,
  );

  const res =
    me.status === 200
      ? NextResponse.json(me.body)
      : NextResponse.json({ detail: extractDetail(me.body) }, { status: me.status });
  return setSessionToken(res, token);
}

export async function readSessionUser(): Promise<NextResponse> {
  const { cookies } = await import("next/headers");
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const me = await backendRequest<Record<string, unknown> | { detail: unknown }>(
    "/auth/me",
    token,
  );
  return NextResponse.json(me.body, { status: me.status });
}

function extractDetail(body: unknown): string {
  if (typeof body === "object" && body !== null) {
    const detail = (body as Record<string, unknown>).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((d) =>
          typeof d === "object" && d !== null
            ? String((d as { msg?: string }).msg ?? "")
            : String(d),
        )
        .join("; ");
    }
  }
  return "Request failed";
}