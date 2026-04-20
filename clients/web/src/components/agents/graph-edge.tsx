"use client";

/**
 * GraphEdgeComponent — SVG edge with octogent-style activity dots.
 *
 * Active edges show 3 staggered dot pairs flowing along a Bezier path:
 * - Trail dots: blurred glow with warm drop-shadows
 * - Core dots: bright cream (#fff4cc) with colored border
 * - Stagger: 0.62s between each dot pair
 * - Duration: 1.9s per traversal
 */

const DOT_INDICES = [0, 1, 2] as const;
const DURATION = 1.9;
const STAGGER = 0.62;

interface GraphEdgeProps {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  active: boolean;
  color: string;
  edgeId: string;
  sourceRadius?: number;
  targetRadius?: number;
}

export function GraphEdgeComponent({
  sourceX,
  sourceY,
  targetX,
  targetY,
  active,
  color,
  edgeId,
  sourceRadius = 48,
  targetRadius = 32,
}: GraphEdgeProps) {
  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  const dist = Math.hypot(dx, dy);
  if (dist < 1) return null;

  const nx = dx / dist;
  const ny = dy / dist;
  const sx = sourceX + nx * (sourceRadius + 6);
  const sy = sourceY + ny * (sourceRadius + 6);
  const tx = targetX - nx * (targetRadius + 6);
  const ty = targetY - ny * (targetRadius + 6);

  const offset = Math.max(16, Math.min(32, dist * 0.16));
  const mx = (sx + tx) / 2 - (ty - sy) / dist * offset;
  const my = (sy + ty) / 2 + (tx - sx) / dist * offset;
  const pathD = `M ${sx} ${sy} Q ${mx} ${my} ${tx} ${ty}`;
  const pathId = `edge-path-${edgeId}`;

  return (
    <g>
      <path
        id={pathId}
        d={pathD}
        fill="none"
        stroke={active ? color : "#374151"}
        strokeWidth={active ? 2 : 1}
        opacity={active ? 0.5 : 0.15}
        strokeDasharray={active ? "none" : "4 4"}
      />

      {active && DOT_INDICES.map((i) => {
        const begin = `${i * STAGGER}s`;
        const trailOpacity = [0.28, 0.24, 0.20][i];
        const coreOpacity = [1.0, 0.92, 0.84][i];

        return (
          <g key={i}>
            <circle
              r={3.8}
              fill={color}
              opacity={trailOpacity}
              className="canvas-edge-dot-trail"
            >
              <animateMotion dur={`${DURATION}s`} repeatCount="indefinite" begin={begin}>
                <mpath href={`#${pathId}`} />
              </animateMotion>
              <animate
                attributeName="r"
                values="3.8;5.2;3.8"
                dur={`${DURATION}s`}
                repeatCount="indefinite"
                begin={begin}
              />
            </circle>

            <circle
              r={2.8}
              fill="#fff4cc"
              stroke={color}
              strokeWidth={1.2}
              opacity={coreOpacity}
              className="canvas-edge-dot-core"
            >
              <animateMotion dur={`${DURATION}s`} repeatCount="indefinite" begin={begin}>
                <mpath href={`#${pathId}`} />
              </animateMotion>
              <animate
                attributeName="r"
                values="2.8;3.8;2.8"
                dur={`${DURATION}s`}
                repeatCount="indefinite"
                begin={begin}
              />
            </circle>
          </g>
        );
      })}
    </g>
  );
}
