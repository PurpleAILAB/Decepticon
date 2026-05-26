// Next.js instrumentation hook — runs once when the server starts. We use it
// to prune trashed engagement workspaces older than 30 days (Linux / Windows
// fallback path; macOS Trash is managed by the OS).
//
// Safe to no-op everywhere: pruneTrash is itself idempotent and ignores a
// missing `.trash/` directory.

export async function register() {
  // Only run in the Node.js runtime — the edge runtime can't do filesystem
  // I/O and would crash on import of `node:fs`.
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  const path = await import("node:path");
  const { pruneTrash } = await import("@/lib/safe-delete");

  const workspacePath =
    process.env.WORKSPACE_PATH ??
    path.join(process.env.HOME ?? "", ".decepticon", "workspace");

  try {
    await pruneTrash(workspacePath);
  } catch (err) {
    // Never block server startup on prune failures.
    console.error("[instrumentation] pruneTrash failed:", err);
  }
}
