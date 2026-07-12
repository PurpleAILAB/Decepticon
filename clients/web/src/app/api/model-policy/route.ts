import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { readModelPolicy, writeModelPolicy } from "@/lib/model-policy";
import { NextRequest, NextResponse } from "next/server";

export async function GET() {
  try {
    await requireAuth();
    return NextResponse.json(await readModelPolicy());
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("GET /api/model-policy error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal server error" },
      { status: 500 },
    );
  }
}

export async function PATCH(req: NextRequest) {
  try {
    await requireAuth();
    const body = await req.json();
    if (!Array.isArray(body.blockedPatterns)) {
      return NextResponse.json(
        { error: "blockedPatterns must be an array" },
        { status: 400 },
      );
    }
    return NextResponse.json(await writeModelPolicy(body.blockedPatterns));
  } catch (e) {
    if (e instanceof AuthError) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("PATCH /api/model-policy error:", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal server error" },
      { status: 500 },
    );
  }
}
