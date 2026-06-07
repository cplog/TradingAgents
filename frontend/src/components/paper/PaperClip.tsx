import { type CSSProperties } from "react";

export type PaperClipProps = {
  size?: number;
  color?: string;
  className?: string;
  style?: CSSProperties;
};

export function PaperClip({
  size = 28,
  color = "var(--color-ink-muted)",
  className,
  style,
}: PaperClipProps) {
  const stroke = size * 0.07;
  const d = [
    `M ${size * 0.6} ${size * 0.1}`,
    `L ${size * 0.25} ${size * 0.1}`,
    `Q ${size * 0.1} ${size * 0.1} ${size * 0.1} ${size * 0.25}`,
    `L ${size * 0.1} ${size * 0.78}`,
    `Q ${size * 0.1} ${size * 0.92} ${size * 0.25} ${size * 0.92}`,
    `L ${size * 0.78} ${size * 0.92}`,
    `Q ${size * 0.92} ${size * 0.92} ${size * 0.92} ${size * 0.78}`,
    `L ${size * 0.92} ${size * 0.32}`,
    `Q ${size * 0.92} ${size * 0.18} ${size * 0.78} ${size * 0.18}`,
    `L ${size * 0.42} ${size * 0.18}`,
  ].join(" ");
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={className}
      style={style}
      aria-hidden="true"
      focusable="false"
    >
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.55"
      />
    </svg>
  );
}
