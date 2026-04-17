/**
 * CLI version — read from package.json at runtime.
 *
 * We use runtime fs.readFileSync (not JSON import) because the CLI's
 * tsconfig rootDir is src/ and package.json lives outside src/.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

function readVersion(): string {
  try {
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = dirname(__filename);
    // version.ts → src/utils/version.ts → ../../package.json
    const pkgPath = join(__dirname, "..", "..", "package.json");
    const pkg = JSON.parse(readFileSync(pkgPath, "utf8")) as { version?: string };
    return pkg.version ?? "0.0.0";
  } catch {
    return "0.0.0";
  }
}

export const CLI_VERSION = readVersion();
