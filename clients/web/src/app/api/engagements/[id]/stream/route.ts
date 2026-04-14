import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { NextRequest, NextResponse } from "next/server";

/**
 * Agent execution stream — only triggers when explicitly requested via POST.
 * GET returns 405 to prevent accidental execution on page load.
 */

export async function GET() {
  return NextResponse.json(
    { error: "Use POST to start agent execution stream" },
    { status: 405 }
  );
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try { await requireAuth(); } catch (e) {
    if (e instanceof AuthError) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    throw e;
  }

  const { id } = await params;
  const body = await req.json().catch(() => ({}));
  const assistantId = (body as Record<string, unknown>).assistantId ?? "decepticon";
  const langGraphUrl = process.env.LANGGRAPH_API_URL ?? "http://localhost:2024";

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const sendEvent = (data: Record<string, unknown>) => {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify(data)}\n\n`)
        );
      };

      try {
        const res = await fetch(`${langGraphUrl}/runs/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            assistant_id: assistantId,
            thread_id: id,
            input: {
              messages: [
                {
                  role: "human",
                  content: `Start engagement ${id}. Execute the full engagement loop.`,
                },
              ],
            },
            stream_mode: "custom",
          }),
        });

        if (!res.ok) {
          sendEvent({
            type: "error",
            content: `LangGraph API error: ${res.status}`,
          });
          controller.close();
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) {
          sendEvent({ type: "error", content: "No response body" });
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
              const jsonStr = trimmed.slice(6);
              try {
                const event = JSON.parse(jsonStr);
                sendEvent(event);
              } catch {
                sendEvent({ type: "raw", content: jsonStr });
              }
            }
          }
        }

        sendEvent({ type: "complete" });
      } catch (err: unknown) {
        sendEvent({
          type: "error",
          content: `Stream error: ${err instanceof Error ? err.message : String(err)}`,
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
