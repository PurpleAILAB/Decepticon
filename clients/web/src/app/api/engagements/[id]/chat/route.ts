import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { NextRequest, NextResponse } from "next/server";

const LANGGRAPH_URL = process.env.LANGGRAPH_API_URL ?? "http://localhost:2024";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try { await requireAuth(); } catch (e) {
    if (e instanceof AuthError) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    throw e;
  }

  const { id } = await params;
  const { message, assistantId } = await req.json();

  if (!message) {
    return NextResponse.json({ error: "Message required" }, { status: 400 });
  }

  const agent = assistantId ?? "soundwave";

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (data: Record<string, unknown>) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      try {
        const res = await fetch(`${LANGGRAPH_URL}/runs/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            assistant_id: agent,
            thread_id: id,
            input: {
              messages: [{ role: "human", content: message }],
            },
            stream_mode: "custom",
          }),
        });

        if (!res.ok) {
          send({ type: "error", content: `LangGraph error: ${res.status}` });
          controller.close();
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) {
          send({ type: "error", content: "No response body" });
          controller.close();
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith(":")) continue;
            if (trimmed.startsWith("data: ")) {
              try {
                const event = JSON.parse(trimmed.slice(6));
                send(event);
              } catch {
                // Forward as text chunk
                send({ type: "text", content: trimmed.slice(6) });
              }
            }
          }
        }

        send({ type: "done" });
      } catch (err: unknown) {
        send({
          type: "error",
          content: err instanceof Error ? err.message : "Stream failed",
        });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
