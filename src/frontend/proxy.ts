import { NextResponse, type NextRequest } from "next/server";

/**
 * Requests to `/api/v1/*` are proxied to the backend API. The session token is
 * read from the HttpOnly cookie and injected as an `Authorization` header so
 * the browser never holds the token. Protected pages check the cookie and
 * redirect to /login when the session is missing.
 */

const PRIVATE_PREFIXES = [
  "/dashboard",
  "/profile",
  "/resumes",
  "/connections",
];

const PUBLIC_ONLY_PREFIXES = ["/login", "/register"];

const TOKEN_COOKIE = "access_token";

const API_BASE = process.env.API_BASE_URL ?? "http://localhost:8000";

function isProtected(pathname: string): boolean {
  return PRIVATE_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}

function isPublicOnly(pathname: string): boolean {
  return PUBLIC_ONLY_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}

export function proxy(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;

  if (pathname.startsWith("/api/v1")) {
    const sessionToken = request.cookies.get(TOKEN_COOKIE)?.value;
    const target = new URL(`${API_BASE}${pathname}${search}`);
    const headers = new Headers(request.headers);
    if (sessionToken) {
      headers.set("Authorization", `Bearer ${sessionToken}`);
    }
    return NextResponse.rewrite(target, {
      request: {
        headers,
      },
    });
  }

  const hasSession = Boolean(request.cookies.get(TOKEN_COOKIE)?.value);

  if (isProtected(pathname) && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }

  if (isPublicOnly(pathname) && hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/profile/:path*",
    "/resumes/:path*",
    "/connections/:path*",
    "/login/:path*",
    "/register/:path*",
    "/api/v1/:path*",
  ],
};