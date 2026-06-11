/**
 * Per-engagement workspace path helper — mirrors `clients/web/src/lib/workspace.ts`
 * and the launcher's `picker.go` so CLI-side writes land in the same
 * per-engagement subdir that `GuidanceMiddleware._resolve_workspace_path`
 * drains on the agent side (see PR superseding #636).
 */

import * as path from "node:path";
import * as os from "node:os";

export const SLUG_RE = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;

export function resolveEngagementDir(name: string, workspace: string): string {
  const root = path.resolve(workspace);
  const dir = path.resolve(root, name);
  if (dir !== root && !dir.startsWith(root + path.sep)) {
    throw new Error("invalid engagement path");
  }
  return dir;
}

export function defaultWorkspaceRoot(): string {
  return (
    process.env.DECEPTICON_WORKSPACE_PATH ??
    path.join(os.homedir(), ".decepticon", "workspace")
  );
}

export function resolveCliEngagementDir(): string | null {
  const slug = process.env.DECEPTICON_ENGAGEMENT;
  if (!slug || !SLUG_RE.test(slug)) return null;
  return resolveEngagementDir(slug, defaultWorkspaceRoot());
}
