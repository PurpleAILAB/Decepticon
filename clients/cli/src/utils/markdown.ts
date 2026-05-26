/**
 * Terminal markdown renderer using marked + marked-terminal.
 * Returns ANSI-formatted string that Ink's <Text> can render directly.
 */

import { marked } from "marked";
import { markedTerminal } from "marked-terminal";



export function renderMarkdown(text: string): string {
  const width = (process.stdout.columns || 80) - 4;
  marked.use(
    markedTerminal({
      showSectionPrefix: false,
      reflowText: true,
      width,
    }),
  );
  try {
    return (marked.parse(text) as string).trimEnd();
  } catch {
    return text;
  }
}
