import { useGLTF } from "@react-three/drei";
import { AGENT_DISPLAY_CONFIG } from "@/lib/agents";

// Preload all GLB models at module evaluation time.
// This starts fetching before any component mounts, eliminating
// the emoji fallback flash. The second arg enables Draco decoding.
for (const [id, meta] of Object.entries(AGENT_DISPLAY_CONFIG)) {
  if (meta.hasModel) {
    useGLTF.preload(`/models/${id}.glb`, true);
  }
}
