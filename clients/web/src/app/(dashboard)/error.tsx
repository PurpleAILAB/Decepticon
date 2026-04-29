"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[Dashboard] Error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4">
      <div className="rounded-xl bg-red-500/10 p-6 ring-1 ring-red-500/20 max-w-lg">
        <h2 className="text-lg font-semibold text-red-300">Dashboard Error</h2>
        <p className="mt-2 text-sm text-red-400/70">
          {error.message || "Failed to load this page."}
        </p>
        <div className="mt-4 flex gap-2">
          <button
            onClick={reset}
            className="rounded-lg bg-red-500/20 px-4 py-2 text-sm font-medium text-red-300 hover:bg-red-500/30"
          >
            Try again
          </button>
          <Link
            href="/"
            className="rounded-lg bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-700"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}
