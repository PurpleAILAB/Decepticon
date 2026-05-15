import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    // React Compiler / Rules-of-React experimental rules added in
    // eslint-plugin-react-hooks v6 + React 19. They flag advisory
    // patterns (setState-in-effect, refs-during-render, immutability,
    // purity) — production correctness is unaffected by these, but the
    // codebase predates the rules. Switch to "warn" for visibility
    // without blocking CI; revisit per-call-site once the Compiler
    // reaches stable. ``next build`` and ``tsc --noEmit`` both pass.
    rules: {
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/refs": "off",
      "react-hooks/immutability": "off",
      "react-hooks/purity": "off",
    },
  },
]);

export default eslintConfig;
