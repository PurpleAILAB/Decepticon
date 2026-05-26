"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Crosshair,
  Radio,
  ClipboardList,
  FileWarning,
  Network,
  Settings,
  Clock,
  FolderOpen,
  Download,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface CommandItem {
  id: string;
  label: string;
  shortcut?: string;
  icon: typeof Search;
  action: () => void;
  section: string;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const router = useRouter();
  const pathname = usePathname();

  // Extract engagement ID from current path
  const engMatch = pathname.match(/^\/engagements\/([^/]+)/);
  const engId = engMatch?.[1] ?? null;

  const commands: CommandItem[] = [
    // Global
    { id: "home", label: "Go to Dashboard", shortcut: "G D", icon: LayoutDashboard, action: () => router.push("/"), section: "Navigation" },
    { id: "engagements", label: "Go to Engagements", shortcut: "G E", icon: Crosshair, action: () => router.push("/engagements"), section: "Navigation" },
    { id: "settings", label: "Go to Settings", icon: Settings, action: () => router.push("/settings"), section: "Navigation" },
    { id: "graph", label: "Go to Attack Graph", icon: Network, action: () => router.push("/graph"), section: "Navigation" },
    // Engagement-scoped (only when in an engagement)
    ...(engId ? [
      { id: "live", label: "Go to Live Terminal", shortcut: "G L", icon: Radio, action: () => router.push(`/engagements/${engId}/live`), section: "Engagement" },
      { id: "plan", label: "Go to Plan", shortcut: "G P", icon: ClipboardList, action: () => router.push(`/engagements/${engId}/plan`), section: "Engagement" },
      { id: "timeline", label: "Go to Timeline", icon: Clock, action: () => router.push(`/engagements/${engId}/timeline`), section: "Engagement" },
      { id: "docs", label: "Go to Documents", icon: FolderOpen, action: () => router.push(`/engagements/${engId}/documents`), section: "Engagement" },
      { id: "findings", label: "Go to Findings", shortcut: "G F", icon: FileWarning, action: () => router.push(`/engagements/${engId}/findings`), section: "Engagement" },
      { id: "eng-graph", label: "Go to Engagement Graph", icon: Network, action: () => router.push(`/engagements/${engId}/graph`), section: "Engagement" },
      { id: "export-json", label: "Export Engagement (JSON)", icon: Download, action: () => window.open(`/api/engagements/${engId}/export?format=json`), section: "Actions" },
      { id: "export-md", label: "Export Engagement (Markdown)", icon: Download, action: () => window.open(`/api/engagements/${engId}/export?format=markdown`), section: "Actions" },
    ] : []),
  ];

  const filtered = query
    ? commands.filter((c) => c.label.toLowerCase().includes(query.toLowerCase()))
    : commands;

  // Reset selection when filter changes
  useEffect(() => setSelectedIndex(0), [query]);

  const execute = useCallback((cmd: CommandItem) => {
    setOpen(false);
    setQuery("");
    cmd.action();
  }, []);

  // Keyboard handler
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Ctrl+K or Cmd+K to toggle
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
        return;
      }

      if (!open) return;

      if (e.key === "Escape") {
        setOpen(false);
        setQuery("");
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        if (filtered.length > 0) setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (filtered.length > 0) setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && filtered[selectedIndex]) {
        e.preventDefault();
        execute(filtered[selectedIndex]);
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, filtered, selectedIndex, execute]);

  if (!open) return null;

  // Group by section
  const sections = new Map<string, CommandItem[]>();
  for (const cmd of filtered) {
    const list = sections.get(cmd.section) ?? [];
    list.push(cmd);
    sections.set(cmd.section, list);
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm" onClick={() => { setOpen(false); setQuery(""); }} />

      {/* Palette */}
      <div className="fixed left-1/2 top-[20%] z-50 w-[520px] -translate-x-1/2 overflow-hidden rounded-xl border border-white/[0.1] bg-zinc-900 shadow-2xl">
        {/* Search input */}
        <div className="flex items-center gap-2 border-b border-white/[0.08] px-4 py-3">
          <Search className="h-4 w-4 text-zinc-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command..."
            className="flex-1 bg-transparent text-sm text-white outline-none placeholder:text-zinc-500"
            autoFocus
          />
          <kbd className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">ESC</kbd>
        </div>

        {/* Results */}
        <div className="max-h-[340px] overflow-auto p-2">
          {filtered.length === 0 ? (
            <p className="py-8 text-center text-sm text-zinc-500">No commands found</p>
          ) : (
            Array.from(sections.entries()).map(([section, items]) => (
              <div key={section} className="mb-1">
                <p className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">
                  {section}
                </p>
                {items.map((cmd) => {
                  const globalIdx = filtered.indexOf(cmd);
                  const isSelected = globalIdx === selectedIndex;
                  return (
                    <button
                      key={cmd.id}
                      type="button"
                      onClick={() => execute(cmd)}
                      onMouseEnter={() => setSelectedIndex(globalIdx)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                        isSelected ? "bg-white/[0.08] text-white" : "text-zinc-400 hover:bg-white/[0.04]",
                      )}
                    >
                      <cmd.icon className="h-4 w-4 shrink-0 text-zinc-500" />
                      <span className="flex-1">{cmd.label}</span>
                      {cmd.shortcut && (
                        <kbd className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-600">
                          {cmd.shortcut}
                        </kbd>
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-white/[0.06] px-4 py-2 text-[10px] text-zinc-600">
          <span className="mr-3">↑↓ navigate</span>
          <span className="mr-3">↵ select</span>
          <span>esc close</span>
        </div>
      </div>
    </>
  );
}
