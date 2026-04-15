"use client";

import { createContext, useContext, useRef, type ReactNode } from "react";
import { Canvas } from "@react-three/fiber";
import { View } from "@react-three/drei";

import "./preload-models";

const AgentCanvasCtx = createContext(false);

/** True when inside an AgentCanvasProvider (shared Canvas available) */
export function useAgentCanvas() {
  return useContext(AgentCanvasCtx);
}

/**
 * Provides a single shared WebGL Canvas for all agent 3D views.
 *
 * Uses drei's View + View.Port scissor-test approach:
 * - One full-page Canvas renders all viewports
 * - Each <View> clips to its own DOM element position
 * - Eliminates multiple WebGL context contention
 */
export function AgentCanvasProvider({ children }: { children: ReactNode }) {
  const containerRef = useRef<HTMLDivElement>(null!);

  return (
    <AgentCanvasCtx.Provider value={true}>
      <div
        ref={containerRef}
        style={{ position: "relative", width: "100%", height: "100%" }}
      >
        {children}
        <Canvas
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100vw",
            height: "100vh",
            pointerEvents: "none",
          }}
          gl={{ alpha: true, antialias: true }}
          eventSource={containerRef as React.RefObject<HTMLElement>}
        >
          {/* Lights go inside each <View>, not here — each View has its own scene */}
          <View.Port />
        </Canvas>
      </div>
    </AgentCanvasCtx.Provider>
  );
}
