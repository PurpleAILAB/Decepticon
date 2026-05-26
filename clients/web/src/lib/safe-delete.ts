import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";

const TRASH_RETENTION_DAYS = 30;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

// Slug regex matches `clients/web/src/app/api/engagements/route.ts` and the Go
// launcher's picker. Re-validated here as a defensive measure so that nothing
// reaches `path.join(workspacePath, slug)` with traversal segments — a slug
// like "../../etc" would otherwise let a buggy caller delete arbitrary paths.
const SLUG_RE = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;

function assertSafeSlug(slug: string): void {
  if (!SLUG_RE.test(slug) || slug.includes("/") || slug.includes("..")) {
    throw new Error(`Refusing to delete: unsafe slug "${slug}"`);
  }
}

/**
 * Move an engagement workspace directory to the platform-appropriate
 * recoverable location instead of `rm -rf`-ing it.
 *
 * - macOS: send to user's Trash via osascript (recoverable from Finder).
 * - Linux/Windows/other: move to `<decepticon-home>/.trash/<slug>-<ISO-ts>/`
 *   (recoverable manually; auto-pruned after 30 days by `pruneTrash`).
 *
 * Idempotent — if the target doesn't exist, returns the target path without
 * raising. Throws on hard I/O failures.
 */
export async function safeDeleteEngagement(
  workspacePath: string,
  slug: string,
): Promise<string> {
  assertSafeSlug(slug);
  const target = path.join(workspacePath, slug);
  try {
    await fs.access(target);
  } catch {
    // Already gone — treat as success.
    return target;
  }

  if (process.platform === "darwin") {
    return moveToMacTrash(target);
  }
  return moveToFallbackTrash(target, workspacePath, slug);
}

async function moveToMacTrash(target: string): Promise<string> {
  // osascript: tell Finder to delete the POSIX file -> goes to user's Trash.
  // Works headlessly; no Finder window needs to be open. Double-quotes inside
  // the path are escaped for the AppleScript string literal.
  const escaped = target.replace(/"/g, '\\"');
  const script = `tell application "Finder" to delete POSIX file "${escaped}"`;
  return new Promise((resolve, reject) => {
    const proc = spawn("osascript", ["-e", script]);
    let stderr = "";
    proc.stderr.on("data", (d) => {
      stderr += d.toString();
    });
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code === 0) {
        // Finder owns the actual Trash location; report the original path.
        resolve(target);
      } else {
        reject(new Error(`osascript exited ${code}: ${stderr.trim()}`));
      }
    });
  });
}

async function moveToFallbackTrash(
  target: string,
  workspacePath: string,
  slug: string,
): Promise<string> {
  // Move into <decepticon-home>/.trash/<slug>-<ISO-timestamp>/. The
  // decepticon home is the parent of WORKSPACE (e.g. ~/.decepticon or the
  // value of WORKSPACE_PATH's parent).
  const decepticonHome = path.resolve(workspacePath, "..");
  const trashDir = path.join(decepticonHome, ".trash");
  await fs.mkdir(trashDir, { recursive: true });
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const dest = path.join(trashDir, `${slug}-${ts}`);
  await fs.rename(target, dest);
  return dest;
}

/**
 * Remove entries in `<decepticon-home>/.trash/` older than 30 days
 * (based on directory mtime). Idempotent and safe to call at server
 * startup — a missing `.trash/` directory is a no-op.
 */
export async function pruneTrash(workspacePath: string): Promise<void> {
  const decepticonHome = path.resolve(workspacePath, "..");
  const trashDir = path.join(decepticonHome, ".trash");
  let entries;
  try {
    entries = await fs.readdir(trashDir, { withFileTypes: true });
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return;
    throw err;
  }
  const cutoff = Date.now() - TRASH_RETENTION_DAYS * MS_PER_DAY;
  await Promise.all(
    entries.map(async (e) => {
      const entryPath = path.join(trashDir, e.name);
      try {
        const stat = await fs.stat(entryPath);
        if (stat.mtimeMs < cutoff) {
          await fs.rm(entryPath, { recursive: true, force: true });
        }
      } catch {
        // best-effort; skip entries we can't stat or remove
      }
    }),
  );
}
