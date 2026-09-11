import type { NextRequest } from "next/server";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const { createSession } = await import("@/lib/auth-server");
  const body = await req.json();
  return createSession("/auth/login", body);
}