"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { useGLTF, Bounds, Center, OrbitControls, View, Environment, PerspectiveCamera } from "@react-three/drei";
import type { Group } from "three";

interface AgentSceneProps {
  agentId: string;
  color: string;
  size: number;
  interactive: boolean;
}

function Model({ url, color }: { url: string; color: string }) {
  const { scene } = useGLTF(url, true);
  const ref = useRef<Group>(null);
  const elapsed = useRef(0);

  useFrame((_, delta) => {
    if (!ref.current) return;
    elapsed.current += delta;
    ref.current.rotation.y = elapsed.current * 0.3;
    ref.current.position.y = Math.sin(elapsed.current * 1.2) * 0.08;
  });

  return (
    <group ref={ref}>
      <Center>
        <primitive object={scene.clone()} />
      </Center>
      <pointLight color={color} intensity={2} distance={5} position={[1, 1, 1]} />
    </group>
  );
}

export function AgentScene({ agentId, color, size, interactive }: AgentSceneProps) {
  return (
    <View
      style={{
        width: size,
        height: size,
        overflow: "visible",
        pointerEvents: interactive ? "auto" : "none",
      }}
    >
      <PerspectiveCamera makeDefault position={[0, 0.3, 2.5]} fov={50} />
      <ambientLight intensity={0.8} />
      <directionalLight position={[5, 5, 5]} intensity={1.5} />
      <Environment preset="city" />
      <Bounds fit clip observe margin={1.2}>
        <Model url={`/models/${agentId}.glb`} color={color} />
      </Bounds>
      {interactive && (
        <OrbitControls enableZoom={false} enablePan={false} />
      )}
    </View>
  );
}
