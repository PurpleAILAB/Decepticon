"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Shield, Crosshair, Network, FileWarning, Lock } from "lucide-react";
import { isAuthEnabled } from "@/lib/auth-bridge";
/* eslint-disable @next/next/no-img-element */

const features = [
  {
    icon: Crosshair,
    title: "Autonomous Red Team",
    description: "AI agents execute security objectives autonomously",
  },
  {
    icon: Network,
    title: "Attack Graph",
    description: "Neo4j-powered kill chain visualization",
  },
  {
    icon: FileWarning,
    title: "Vulnerability Discovery",
    description: "Structured findings with severity classification",
  },
  {
    icon: Lock,
    title: "Offensive Vaccine",
    description: "Attack-defend-verify feedback loop",
  },
];

export default function LoginPage() {
  const router = useRouter();

  // OSS mode — no auth, redirect to dashboard
  useEffect(() => {
    if (!isAuthEnabled()) {
      router.replace("/");
    }
  }, [router]);

  if (!isAuthEnabled()) {
    return null;
  }

  // SaaS mode — EE auth handles sign-in
  // The actual signIn function is provided by the EE auth module
  async function handleSignIn() {
    const ee = (await import("@/lib/ee")).getEE();
    // EE auth provides the sign-in flow
    if (ee.auth) {
      // EE handles the full OAuth redirect flow
      window.location.href = "/api/auth/signin";
    }
  }

  return (
    <div className="flex min-h-screen bg-background">
      {/* Left panel — branding */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950 p-12 lg:flex">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:64px_64px]" />
        <div className="absolute left-1/2 top-1/2 h-[600px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-red-500/5 blur-3xl" />

        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="PurpleAILab" width={40} height={40} />
            <div>
              <h1 className="text-lg font-bold tracking-tight text-foreground">
                DECEPTICON
              </h1>
              <p className="text-xs text-muted-foreground">
                Autonomous Red Team Platform
              </p>
            </div>
          </div>
        </div>

        <div className="relative z-10 space-y-8">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-foreground">
              Continuous Threat
              <br />
              Exposure Management
            </h2>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
              AI-powered autonomous security testing that discovers, validates,
              and verifies vulnerabilities across your entire attack surface.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="rounded-lg border border-white/5 bg-white/[0.02] p-4 backdrop-blur-sm"
              >
                <feature.icon className="mb-2 h-4 w-4 text-red-400/80" />
                <h3 className="text-sm font-medium text-foreground">
                  {feature.title}
                </h3>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10">
          <p className="text-xs text-muted-foreground/50">
            &copy; {new Date().getFullYear()} Purple AI Lab. All rights reserved.
          </p>
        </div>
      </div>

      {/* Right panel — login form */}
      <div className="flex w-full flex-col items-center justify-center px-6 lg:w-1/2">
        <div className="mb-8 flex items-center gap-2 lg:hidden">
          <img src="/logo.png" alt="PurpleAILab" width={28} height={28} />
          <span className="text-lg font-bold">DECEPTICON</span>
        </div>

        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-2 text-center">
            <h2 className="text-2xl font-bold tracking-tight">Welcome back</h2>
            <p className="text-sm text-muted-foreground">
              Sign in to your account to continue
            </p>
          </div>

          <Button
            size="lg"
            className="w-full gap-3 bg-white text-black hover:bg-white/90"
            onClick={handleSignIn}
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
            </svg>
            Continue with GitHub
          </Button>

          <div className="relative">
            <Separator />
            <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-background px-2 text-xs text-muted-foreground">
              secure authentication
            </span>
          </div>

          <div className="space-y-3 rounded-lg border border-border/50 bg-card/50 p-4">
            <div className="flex items-start gap-3">
              <Lock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p className="text-xs font-medium text-foreground">
                  GitHub OAuth 2.0
                </p>
                <p className="text-xs text-muted-foreground">
                  We use GitHub for authentication and repository access. No
                  passwords stored.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Shield className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p className="text-xs font-medium text-foreground">
                  Scoped permissions
                </p>
                <p className="text-xs text-muted-foreground">
                  Read-only repo access for code scanning targets. No write
                  permissions requested.
                </p>
              </div>
            </div>
          </div>

          <p className="text-center text-xs text-muted-foreground/60">
            By continuing, you agree to our Terms of Service and Privacy Policy.
          </p>
        </div>
      </div>
    </div>
  );
}
