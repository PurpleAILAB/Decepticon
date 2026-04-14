import { NextResponse } from "next/server";
import { getEE } from "@/lib/ee";

/**
 * NextAuth.js route handler — only active when EE auth is configured.
 * In OSS mode, returns 404 (no auth system).
 */

function notConfigured() {
  return NextResponse.json(
    { error: "Authentication not configured. Install @decepticon/ee for auth support." },
    { status: 404 }
  );
}

export async function GET() {
  const ee = getEE();
  if (!ee.auth) return notConfigured();
  // EE wires NextAuth handlers externally — this route delegates
  // In the full EE setup, the EE package provides middleware that handles auth routes
  return notConfigured();
}

export async function POST() {
  const ee = getEE();
  if (!ee.auth) return notConfigured();
  return notConfigured();
}
