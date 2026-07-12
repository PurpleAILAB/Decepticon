"use client";

/* eslint-disable @next/next/no-img-element */

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Crosshair,
  Radio,
  ClipboardList,
  Clock,
  FolderOpen,
  FileWarning,
  Network,
  Settings,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Bell,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { EngagementModelPicker, type ModelOverrides } from "@/components/engagement/engagement-model-picker";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";
import { useState, useEffect } from "react";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  engagementScoped?: boolean;
}

const globalNav: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/engagements", label: "Engagements", icon: Crosshair },
];

const engagementNav: NavItem[] = [
  { href: "/live", label: "Live", icon: Radio, engagementScoped: true },
  { href: "/plan", label: "Plan", icon: ClipboardList, engagementScoped: true },
  { href: "/timeline", label: "Timeline", icon: Clock, engagementScoped: true },
  { href: "/documents", label: "Documents", icon: FolderOpen, engagementScoped: true },
  { href: "/findings", label: "Findings", icon: FileWarning, engagementScoped: true },
  { href: "/graph", label: "Attack Graph", icon: Network, engagementScoped: true },
];

const bottomNav: NavItem[] = [
  { href: "/settings", label: "Settings", icon: Settings },
];

interface Engagement {
  id: string;
  name: string;
  modelOverride?: string | null;
  modelOverrides?: ModelOverrides | null;
}

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [engDropdownOpen, setEngDropdownOpen] = useState(false);
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [activeEngagement, setActiveEngagement] = useState<Engagement | null>(null);

  // Derive engagement ID from pathname — only refetch when engagement context changes
  const engMatch = pathname.match(/^\/engagements\/([^/]+)/);
  const activeEngId = engMatch?.[1] ?? null;

  useEffect(() => {
    let cancelled = false;
    fetch("/api/engagements")
      .then((res) => {
        if (!res.ok) throw new Error("fetch failed");
        return res.json();
      })
      .then((data: Engagement[]) => {
        if (!cancelled) setEngagements(data);
      })
      .catch(() => {
        if (!cancelled) setEngagements([]);
      });
    return () => { cancelled = true; };
  }, [activeEngId]);

  useEffect(() => {
    if (!activeEngId) {
      setActiveEngagement(null);
      return;
    }

    let cancelled = false;
    fetch(`/api/engagements/${activeEngId}`, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("fetch failed");
        return res.json();
      })
      .then((data: Engagement) => {
        if (!cancelled) setActiveEngagement(data);
      })
      .catch(() => {
        if (!cancelled) setActiveEngagement(null);
      });
    return () => { cancelled = true; };
  }, [activeEngId]);

  const activeEng = activeEngId
    ? activeEngagement ?? engagements.find((e) => e.id === activeEngId) ?? null
    : null;

  function resolveHref(item: NavItem) {
    if (item.engagementScoped && activeEngId) {
      return `/engagements/${activeEngId}${item.href}`;
    }
    return item.href;
  }

  function isActive(item: NavItem) {
    const href = resolveHref(item);
    if (item.href === "/" || item.href === "/engagements") {
      return pathname === item.href;
    }
    return pathname === href || pathname.startsWith(href + "/");
  }

  function renderNavItem(item: NavItem) {
    const href = resolveHref(item);
    const active = isActive(item);
    const disabled = item.engagementScoped && !activeEngId;

    const link = (
      <Link
        key={href}
        href={disabled ? "#" : href}
        className={cn(
          "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150",
          active
            ? "bg-primary/10 text-primary shadow-sm shadow-primary/5"
            : disabled
              ? "cursor-not-allowed text-muted-foreground/30"
              : "text-muted-foreground hover:bg-accent hover:text-foreground"
        )}
        onClick={(e) => disabled && e.preventDefault()}
      >
        <item.icon className={cn("h-4 w-4 shrink-0", active && "text-primary")} />
        {!collapsed && <span>{item.label}</span>}
      </Link>
    );

    if (collapsed) {
      return (
        <Tooltip key={href}>
          <TooltipTrigger>{link}</TooltipTrigger>
          <TooltipContent side="right">
            {item.label}
            {disabled && " (select engagement first)"}
          </TooltipContent>
        </Tooltip>
      );
    }

    return link;
  }

  function renderMobileNavItem(item: NavItem) {
    const href = resolveHref(item);
    const active = isActive(item);
    const disabled = item.engagementScoped && !activeEngId;

    return (
      <Link
        key={href}
        href={disabled ? "#" : href}
        aria-label={item.label}
        className={cn(
          "flex min-w-14 flex-col items-center justify-center gap-0.5 rounded-lg px-2 py-1.5 text-[10px] font-medium transition-colors",
          active
            ? "bg-primary/10 text-primary"
            : disabled
              ? "cursor-not-allowed text-muted-foreground/25"
              : "text-muted-foreground hover:bg-accent hover:text-foreground"
        )}
        onClick={(e) => disabled && e.preventDefault()}
      >
        <item.icon className="h-4 w-4 shrink-0" />
        <span className="max-w-14 truncate">{item.label}</span>
      </Link>
    );
  }

  return (
    <>
    <aside
      className={cn(
        "hidden h-full flex-col border-r border-border/50 bg-sidebar transition-all duration-200 md:flex",
        collapsed ? "w-16" : "w-72"
      )}
    >
      {/* Logo */}
      <div className="flex min-h-14 items-center gap-2.5 border-b border-border/50 px-4 py-3">
        <img src="/logo.png" alt="PurpleAILab" width={26} height={26} className="shrink-0" />
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <span className="block truncate text-sm font-bold tracking-tight">
              <span className="text-purple-400">Purple</span>
              <span className="text-foreground">AILab</span>
            </span>
            <div className="mt-0.5 flex min-w-0 items-center gap-2 text-[10px] text-muted-foreground">
              <span className="truncate">Autonomous Red Team Platform</span>
              <span className="rounded-full bg-emerald-500/10 px-1.5 py-0.5 font-medium text-emerald-400">Online</span>
            </div>
            <div className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground" title="Self-hosted Docker instance running on this Windows host">
              <Bell className="size-3" />
              <span>Self-hosted</span>
            </div>
          </div>
        )}
      </div>

      <nav className="flex flex-1 flex-col overflow-y-auto overflow-x-hidden">
        {/* Global nav */}
        <div className="space-y-0.5 p-2">
          {globalNav.map(renderNavItem)}
        </div>

        <div className="px-3">
          <Separator className="opacity-50" />
        </div>

        {/* Engagement context */}
        <div className="p-2">
          {!collapsed && (
            <div className="mb-1 px-3">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50">
                Engagement
              </span>
            </div>
          )}

          {/* Engagement selector */}
          {!collapsed && (
            <div className="relative mb-1">
              <button
                type="button"
                onClick={() => setEngDropdownOpen(!engDropdownOpen)}
                className={cn(
                  "flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors",
                  activeEng
                    ? "bg-accent/50 text-foreground"
                    : "text-muted-foreground hover:bg-accent"
                )}
              >
                <span className="truncate">
                  {activeEng ? activeEng.name : "Select engagement..."}
                </span>
                <ChevronDown className={cn("h-3.5 w-3.5 shrink-0 transition-transform", engDropdownOpen && "rotate-180")} />
              </button>

              {engDropdownOpen && (
                <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-48 overflow-auto rounded-lg border border-border bg-popover p-1 shadow-lg">
                  {engagements.length === 0 ? (
                    <p className="px-2.5 py-1.5 text-xs text-muted-foreground">No engagements</p>
                  ) : (
                    engagements.map((eng) => (
                      <Link
                        key={eng.id}
                        href={`/engagements/${eng.id}`}
                        onClick={() => setEngDropdownOpen(false)}
                        className={cn(
                          "flex items-center rounded-md px-2.5 py-1.5 text-xs transition-colors",
                          eng.id === activeEngId
                            ? "bg-primary/10 text-primary"
                            : "text-muted-foreground hover:bg-accent hover:text-foreground"
                        )}
                      >
                        <span className="truncate">{eng.name}</span>
                      </Link>
                    ))
                  )}
                </div>
              )}
            </div>
          )}

          {/* Engagement-scoped nav */}
          <div className="space-y-0.5">
            {engagementNav.map(renderNavItem)}
          </div>

          {!collapsed && activeEngagement && (
            <div className="mt-3">
              <EngagementModelPicker
                engagementId={activeEngagement.id}
                value={activeEngagement.modelOverride ?? ""}
                overrides={activeEngagement.modelOverrides ?? null}
                variant="sidebar"
                onChange={(modelOverride, modelOverrides) => {
                  setActiveEngagement((current) =>
                    current
                      ? {
                          ...current,
                          modelOverride: modelOverride || null,
                          modelOverrides,
                        }
                      : current,
                  );
                }}
              />
            </div>
          )}
        </div>

        <div className="min-h-4 flex-1" />

        {/* Bottom nav */}
        <div className="space-y-0.5 p-2">
          {bottomNav.map(renderNavItem)}
        </div>
      </nav>

      {/* Collapse toggle */}
      <div className="border-t border-border/50 p-2">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-center text-muted-foreground hover:text-foreground"
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>
    </aside>
    <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-border/60 bg-sidebar/95 px-2 py-1.5 backdrop-blur md:hidden">
      <div className="flex gap-1 overflow-x-auto">
        {[...globalNav, ...engagementNav, ...bottomNav].map(renderMobileNavItem)}
      </div>
    </nav>
    </>
  );
}
