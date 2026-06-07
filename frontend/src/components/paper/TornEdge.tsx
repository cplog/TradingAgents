import { type CSSProperties } from "react";

export type TornEdgeProps = {
  width?: number;
  height?: number;
  side?: "top" | "bottom";
  fill?: string;
  segments?: number;
  className?: string;
  style?: CSSProperties;
};

function tornPath(
  width: number,
  height: number,
  side: "top" | "bottom",
  segments: number,
): string {
  const baseY = side === "top" ? 0 : height;
  const tearY = side === "top" ? height * 0.18 : height * 0.82;
  const step = width / segments;
  const pts: string[] = [];
  for (let i = 0; i <= segments; i++) {
    const x = i * step;
    const wobble = Math.sin(i * 1.7) * (height * 0.05) + (i % 2 === 0 ? -1 : 1) * 0.6;
    const y = tearY + wobble;
    pts.push(`${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`);
  }
  if (side === "top") {
    pts.push(`L ${width} 0`);
    pts.push(`L 0 0`);
  } else {
    pts.push(`L ${width} ${height}`);
    pts.push(`L 0 ${height}`);
  }
  pts.push("Z");
  return pts.join(" ");
}

export function TornEdge({
  width = 280,
  height = 18,
  side = "bottom",
  fill = "var(--color-paper-card)",
  segments = 14,
  className,
  style,
}: TornEdgeProps) {
  const d = tornPath(width, height, side, segments);
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      style={style}
      aria-hidden="true"
      focusable="false"
    >
      <path d={d} fill={fill} />
    </svg>
  );
}
