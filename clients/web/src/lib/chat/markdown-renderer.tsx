"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { MessageRenderer } from "./types";

/**
 * Markdown message renderer — renders assistant content as rich markdown.
 *
 * This is the default renderer. When OpenUI GenUI is enabled, swap this
 * for OpenUIRenderer which renders LLM output as native shadcn components.
 */
export class MarkdownMessageRenderer implements MessageRenderer {
  renderAssistantContent(content: string): React.ReactNode {
    return (
      <div className="text-sm leading-relaxed text-zinc-200 [&_pre]:my-2 [&_pre]:rounded-lg [&_pre]:bg-black/40 [&_pre]:p-3 [&_pre]:ring-1 [&_pre]:ring-white/5 [&_code]:text-xs [&_code]:text-amber-400/80 [&_p]:my-1.5 [&_p]:text-zinc-300 [&_ul]:my-1.5 [&_ul]:pl-4 [&_ul]:list-disc [&_ol]:my-1.5 [&_ol]:pl-4 [&_ol]:list-decimal [&_li]:my-0.5 [&_li]:text-zinc-300 [&_h1]:text-base [&_h1]:font-bold [&_h1]:text-white [&_h1]:mt-3 [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:text-white [&_h2]:mt-2 [&_h3]:text-sm [&_h3]:font-medium [&_h3]:text-white [&_strong]:text-white [&_em]:text-zinc-400 [&_table]:my-2 [&_table]:w-full [&_table]:text-xs [&_th]:px-2.5 [&_th]:py-1.5 [&_th]:text-left [&_th]:text-zinc-500 [&_th]:font-medium [&_th]:border-b [&_th]:border-white/5 [&_td]:px-2.5 [&_td]:py-1.5 [&_td]:text-zinc-300 [&_td]:border-b [&_td]:border-white/[0.03] [&_a]:text-red-400 [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-red-500/30 [&_blockquote]:pl-3 [&_blockquote]:text-zinc-400">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    );
  }

  renderToolOutput(content: string): React.ReactNode {
    return (
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-zinc-400">
        {content}
      </pre>
    );
  }
}

/**
 * Singleton instance — use this in components.
 * When OpenUI is ready, swap this export for OpenUIRenderer.
 */
export const defaultRenderer = new MarkdownMessageRenderer();
