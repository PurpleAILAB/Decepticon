"use client";

import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export function Header() {
  return (
    <header className="flex h-12 items-center justify-between gap-2 border-b border-border/50 bg-background/80 px-3 backdrop-blur-sm md:h-14 md:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-2 md:gap-3">
        <h2 className="truncate text-xs font-medium text-muted-foreground sm:text-sm">
          Autonomous Red Team Platform
        </h2>
        <Separator orientation="vertical" className="hidden h-4 sm:block" />
        <span className="hidden rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400 sm:inline-flex">
          Online
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground">
          <Bell className="h-4 w-4" />
        </Button>
        <span
          className="hidden text-xs text-muted-foreground sm:inline"
          title="Self-hosted Docker instance running on this Windows host"
        >
          Self-hosted
        </span>
      </div>
    </header>
  );
}
