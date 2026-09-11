import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function GET() {
  const { readSessionUser } = await import("@/lib/auth-server");
  return readSessionUser();
}

export async function POST() {
  const { clearSessionToken } = await import("@/lib/auth-server");
  return clearSessionToken(NextResponse.json({ ok: true }));
}