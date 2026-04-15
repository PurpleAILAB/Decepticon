"use client";

import { useState, useEffect, useRef } from "react";
import { AGENTS, type AgentConfig } from "@/lib/agents";

interface UseAgentsReturn {
  agents: AgentConfig[];
  isLoading: boolean;
}

const CACHE_TTL = 60_000; // 1 minute

let cachedAgents: AgentConfig[] | null = null;
let cacheTime = 0;

/**
 * Fetch available agents from the backend, with static fallback.
 * Initial render uses the static AGENTS array (no loading flash).
 * Background fetch updates the list when the backend is reachable.
 */
export function useAgents(): UseAgentsReturn {
  const [agents, setAgents] = useState<AgentConfig[]>(cachedAgents ?? AGENTS);
  const [isLoading, setIsLoading] = useState(!cachedAgents);
  const fetched = useRef(false);

  useEffect(() => {
    if (fetched.current) return;
    fetched.current = true;

    // Skip fetch if cache is fresh
    if (cachedAgents && Date.now() - cacheTime < CACHE_TTL) {
      setAgents(cachedAgents);
      setIsLoading(false);
      return;
    }

    fetch("/api/agents")
      .then((res) => {
        if (!res.ok) throw new Error("fetch failed");
        return res.json() as Promise<AgentConfig[]>;
      })
      .then((data) => {
        if (data.length > 0) {
          cachedAgents = data;
          cacheTime = Date.now();
          setAgents(data);
        }
      })
      .catch(() => {
        // Keep static fallback — no error shown to user
      })
      .finally(() => setIsLoading(false));
  }, []);

  return { agents, isLoading };
}
