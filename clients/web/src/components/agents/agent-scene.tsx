"use client";

import { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { useGLTF, OrbitControls, Environment } from "@react-three/drei";
import type { Group } from "three";

interface AgentSceneProps {
  agentId: string;
  color: string;
  size: number;
  interactive: boolean;
}

function Model({ url, color }: { url: string; color: string }) {
  const { scene } = useGLTF(url);
  const ref = useRef<Group>(null);

  useFrame((state) => {
    if (ref.current) {
      ref.current.rotation.y = state.clock.elapsedTime * 0.3;
      ref.current.position.y = Math.sin(state.clock.elapsedTime * 1.2) * 0.08;
    }
  });

  return (
    <group ref={ref}>
      <primitive object={scene.clone()} scale={1.5} />
      <pointLight color={color} intensity={2} distance={5} position={[1, 1, 1]} />
    </group>
  );
}

export function AgentScene({ agentId, color, size, interactive }: AgentSceneProps) {
  return (
    <div style={{ width: size, height: size }} className="rounded-xl overflow-hidden">
      <Canvas
        camera={{ position: [0, 0.5, 3], fov: 40 }}
        style={{ background: "transparent" }}
        gl={{ alpha: true, antialias: true }}
      >
        <ambientLight intensity={0.6} />
        <directionalLight position={[5, 5, 5]} intensity={1.2} />
        <Model url={`/models/${agentId}.glb`} color={color} />
        <Environment preset="city" />
        {interactive && (
          <OrbitControls enableZoom={false} enablePan={false} />
        )}
      </Canvas>
    </div>
  );
}
