import { NextRequest, NextResponse } from "next/server";

// OSS mode: no auth required. Edition check must use NEXT_PUBLIC_*
// because this proxy runs in Edge Runtime (no Node runtime access).
const IS_EE = process.env.NEXT_PUBLIC_DECEPTICON_EDITION === "ee";

export default function proxy(req: NextRequest) {
  // OSS mode: skip all auth redirects — no login required.
  if (!IS_EE) {
    return NextResponse.next();
  }

  const sessionCookie =
    req.cookies.get("authjs.session-token") ??
    req.cookies.get("__Secure-authjs.session-token");
  const isLoggedIn = !!sessionCookie;
  const isLoginPage = req.nextUrl.pathname === "/login";
  const isAuthRoute = req.nextUrl.pathname.startsWith("/api/auth");

  // Allow auth API routes
  if (isAuthRoute) {
    return NextResponse.next();
  }

  // Redirect unauthenticated users to login
  if (!isLoggedIn && !isLoginPage) {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  // Redirect authenticated users away from login
  if (isLoggedIn && isLoginPage) {
    return NextResponse.redirect(new URL("/", req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|favicon.ico|logo.png|api/auth|.*\\.(?:png|jpg|svg|ico|webp)$).*)"],
};
