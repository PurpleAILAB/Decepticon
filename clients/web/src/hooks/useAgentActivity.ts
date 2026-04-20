"use client";

/**
 * useAgentActivity — maps SubagentCustomEvent[] to graph nodes/edges.
 *
 * Uses @decepticon/streaming types directly — no regex parsing.
 * Same event types that the CLI processes, rendered as a graph instead of text.
 */

import { useMemo } from "react";
import type { AgentConfig } from "@/lib/agents";
import type { SubagentCustomEvent } from "@decepticon/streaming";
import type { GraphNode, GraphEdge, AgentRuntimeState } from "@/lib/graph/types";
import { isWaitingState } from "@/lib/graph/types";

const ORCHESTRATOR_RADIUS = 48;
const AGENT_RADIUS = 32;
const TOOL_SESSION_RADIUS = 10;

interface ToolSession {
  id: string;
  agentId: string;
  toolName: string;
  done: boolean;
}

interface UseAgentActivityOptions {
  agents: AgentConfig[];
  events: SubagentCustomEvent[];
}

interface UseAgentActivityReturn {
  nodes: GraphNode[];
  edges: GraphEdge[];
  activeAgentIds: Set<string>;
}

export function useAgentActivity({
  agents,
  events,
}: UseAgentActivityOptions): UseAgentActivityReturn {
  return useMemo(() => {
    const agentStates = new Map<string, AgentRuntimeState>();
    const agentToolNames = new Map<string, string>();
    const activeAgentIds = new Set<string>();
    const toolSessionMap = new Map<string, ToolSession>();

    for (let idx = 0; idx < events.length; idx++) {
      const event = events[idx];
      switch (event.type) {
        case "subagent_start":
          agentStates.set(event.agent, "processing");
          activeAgentIds.add(event.agent);
          break;

        case "subagent_end":
          agentStates.set(event.agent, "completed");
          activeAgentIds.delete(event.agent);
          break;

        case "subagent_tool_call": {
          agentStates.set(event.agent, "processing");
          activeAgentIds.add(event.agent);
          if (event.tool) {
            agentToolNames.set(event.agent, event.tool);
            // One node per unique tool name per agent — no duplicates
            const sessionId = `tool-${event.agent}-${event.tool}`;
            toolSessionMap.set(sessionId, {
              id: sessionId,
              agentId: event.agent,
              toolName: event.tool,
              done: false,
            });
          }
          break;
        }

        case "subagent_tool_result": {
          if (event.tool) {
            const sessionId = `tool-${event.agent}-${event.tool}`;
            const session = toolSessionMap.get(sessionId);
            if (session) session.done = true;
          }
          break;
        }
      }
    }

    // Show all agents — idle ones are dimmed, active ones pulse
    const visibleAgents = agents;

    const nodes: GraphNode[] = [];
    const agentPositions = new Map<string, { x: number; y: number }>();
    const angleStep = (2 * Math.PI) / Math.max(visibleAgents.length - 1, 1); // -1 for orchestrator at center

    let angleIdx = 0;
    for (const agent of visibleAgents) {
      const isOrch = agent.id === "decepticon";
      const runtimeState = agentStates.get(agent.id) ?? (isOrch ? "processing" : "idle");
      const radius = isOrch ? ORCHESTRATOR_RADIUS : AGENT_RADIUS;
      const circleR = 160;
      const angle = angleStep * angleIdx;
      const x = isOrch ? 0 : Math.cos(angle) * circleR;
      const y = isOrch ? 0 : Math.sin(angle) * circleR;
      if (!isOrch) angleIdx++;

      agentPositions.set(agent.id, { x, y });

      nodes.push({
        id: agent.id,
        type: isOrch ? "orchestrator" : "agent",
        x, y,
        vx: 0, vy: 0,
        pinned: isOrch,
        radius,
        agentId: agent.id,
        label: agent.name,
        color: agent.color,
        runtimeState,
        mascotEmoji: agent.mascotEmoji,
        role: agent.role,
        waitingToolName: agentToolNames.get(agent.id),
      });
    }

    // Build tool session satellite nodes (last 5 per agent)
    const sessionsByAgent = new Map<string, ToolSession[]>();
    for (const session of toolSessionMap.values()) {
      const list = sessionsByAgent.get(session.agentId) ?? [];
      list.push(session);
      sessionsByAgent.set(session.agentId, list);
    }

    for (const [agentId, sessions] of sessionsByAgent) {
      const parentPos = agentPositions.get(agentId);
      if (!parentPos) continue;

      const agentConfig = agents.find((a) => a.id === agentId);
      const color = agentConfig?.color ?? "#6b7280";
      const recentSessions = sessions.slice(-5);
      const sessionAngleStep = (2 * Math.PI) / Math.max(recentSessions.length, 1);

      for (let i = 0; i < recentSessions.length; i++) {
        const session = recentSessions[i];
        const angle = sessionAngleStep * i - Math.PI / 2;
        const dist = 60;

        nodes.push({
          id: session.id,
          type: session.done ? "completed-session" : "tool-session",
          x: parentPos.x + Math.cos(angle) * dist,
          y: parentPos.y + Math.sin(angle) * dist,
          vx: 0, vy: 0,
          pinned: false,
          radius: TOOL_SESSION_RADIUS,
          agentId: session.agentId,
          label: session.toolName,
          color,
          runtimeState: session.done ? "completed" : "processing",
          mascotEmoji: "",
          role: "tool",
          parentAgentId: agentId,
        });
      }
    }

    // Build edges
    const edges: GraphEdge[] = [];

    for (const [agentId, state] of agentStates) {
      if (agentId === "decepticon") continue;
      edges.push({
        source: "decepticon",
        target: agentId,
        active: state === "processing" || isWaitingState(state),
      });
    }

    for (const node of nodes) {
      if ((node.type === "tool-session" || node.type === "completed-session") && node.parentAgentId) {
        edges.push({
          source: node.parentAgentId,
          target: node.id,
          active: node.type === "tool-session",
        });
      }
    }

    return { nodes, edges, activeAgentIds };
  }, [agents, events]);
}
