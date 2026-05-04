"use client";

import Image from "next/image";
import type { AgentConfig } from "@/lib/agents";

interface AgentAvatarProps {
  agent: AgentConfig;
  size?: number;
}

/**
 * Agent avatar.
 * Decepticon uses an image; sub-agents render as text initials.
 */
export function AgentAvatar({ agent, size = 64 }: AgentAvatarProps) {
  if (agent.imagePath) {
    return (
      <Image
        src={agent.imagePath}
        alt={agent.name}
        width={size}
        height={size}
        className="select-none object-contain"
        priority={agent.id === "decepticon"}
      />
    );
  }

  const initial = agent.name.trim().charAt(0).toUpperCase();

  return (
    <span
      className="flex select-none items-center justify-center rounded-full border font-semibold"
      style={{
        width: size,
        height: size,
        borderColor: agent.color,
        backgroundColor: `${agent.color}18`,
        color: agent.color,
        fontSize: size * 0.42,
      }}
      aria-label={agent.name}
    >
      {initial}
    </span>
  );
}
