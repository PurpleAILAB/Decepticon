declare module "marked-terminal" {
  import type { MarkedExtension } from "marked";

  interface TerminalRendererOptions {
    showSectionPrefix?: boolean;
    reflowText?: boolean;
    width?: number;
    tab?: number;
  }

  export function markedTerminal(
    options?: TerminalRendererOptions,
  ): MarkedExtension;
}
