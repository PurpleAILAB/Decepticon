"use client";

import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { hasEE } from "@/lib/ee";

function EEUserMenu() {
  // Lazy-load the full user menu only when EE auth is available
  // EE provides SessionProvider + useSession + signOut
  return null; // EE package overrides this via slot
}

export function Header() {
  const showAuth = hasEE();

  return (
    <header className="flex h-14 items-center justify-between border-b border-border/50 bg-background/80 px-6 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          Autonomous Red Team Platform
        </h2>
        <Separator orientation="vertical" className="h-4" />
        <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400">
          Online
        </span>
      </div>

      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground">
          <Bell className="h-4 w-4" />
        </Button>

        {showAuth ? (
          <EEUserMenu />
        ) : (
          <span className="text-xs text-muted-foreground">Local Mode</span>
        )}
      </div>
    </header>
  );
}
