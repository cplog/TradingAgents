import { type CSSProperties } from "react";

export type WashiTapeProps = {
  width?: number;
  height?: number;
  rotation?: number;
  color?: string;
  opacity?: number;
  className?: string;
  style?: CSSProperties;
};

const DEFAULTS = {
  width: 96,
  height: 22,
  rotation: -2,
  color: "var(--color-apricot-soft)",
  opacity: 0.72,
};

export function WashiTape({
  width = DEFAULTS.width,
  height = DEFAULTS.height,
  rotation = DEFAULTS.rotation,
  color = DEFAULTS.color,
  opacity = DEFAULTS.opacity,
  className,
  style,
}: WashiTapeProps) {
  const cy = height / 2;
  const wobble = 0.8;
  const d = [
    `M 0 ${cy - wobble}`,
    `L ${width * 0.18} ${cy - wobble * 0.4}`,
    `L ${width * 0.42} ${cy + wobble * 0.6}`,
    `L ${width * 0.7} ${cy - wobble * 0.3}`,
    `L ${width} ${cy + wobble * 0.5}`,
    `L ${width} ${cy + height / 2}`,
    `L ${width * 0.78} ${cy + height / 2 + wobble * 0.4}`,
    `L ${width * 0.5} ${cy + height / 2 - wobble * 0.3}`,
    `L ${width * 0.22} ${cy + height / 2 + wobble * 0.5}`,
    `L 0 ${cy + height / 2 - wobble * 0.4}`,
    "Z",
  ].join(" ");
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      style={{
        transform: `rotate(${rotation}deg)`,
        filter: "drop-shadow(0 1px 1.5px rgba(120, 80, 40, 0.10))",
        ...style,
      }}
      aria-hidden="true"
      focusable="false"
    >
      <path d={d} fill={color} opacity={opacity} />
      <path
        d={d}
        fill="none"
        stroke="rgba(42, 32, 24, 0.08)"
        strokeWidth="0.5"
        opacity="0.5"
      />
    </svg>
  );
}
