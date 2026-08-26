import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  {
    // The existing V1 codebase predates React Compiler lint rules. Keep the
    // established patterns in scope while enabling the rest of Next's lint set.
    rules: {
      "react-hooks/immutability": "off",
      "react-hooks/refs": "off",
      "react-hooks/set-state-in-effect": "off",
    },
  },
  {
    files: ["**/produtos/precos/page.tsx"],
    rules: {
      // Existing domain helper `useDefault` is not a React hook.
      "react-hooks/rules-of-hooks": "off",
    },
  },
  globalIgnores([".next/**", "node_modules/**"]),
]);
