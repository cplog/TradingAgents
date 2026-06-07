import { type CSSProperties } from "react";
import { WashiTape } from "./WashiTape";

export type WorkspaceSceneProps = {
  width?: number;
  height?: number;
  className?: string;
  style?: CSSProperties;
};

export function WorkspaceScene({
  width = 360,
  height = 280,
  className,
  style,
}: WorkspaceSceneProps) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 360 280"
      className={className}
      style={style}
      aria-hidden="true"
      focusable="false"
      role="img"
    >
      <defs>
        <filter id="ws-grain" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" />
          <feColorMatrix values="0 0 0 0 0.16 0 0 0 0 0.13 0 0 0 0 0.10 0 0 0 0.06 0" />
          <feComposite in2="SourceGraphic" operator="in" />
        </filter>
        <filter id="ws-lift" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur in="SourceAlpha" stdDeviation="2" />
          <feOffset dy="2" />
          <feComponentTransfer>
            <feFuncA type="linear" slope="0.20" />
          </feComponentTransfer>
          <feMerge>
            <feMergeNode />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <g filter="url(#ws-grain)" opacity="0.6">
        <rect x="0" y="0" width="360" height="280" fill="transparent" />
      </g>

      <g transform="translate(48 80) rotate(-1.5)">
        <rect
          x="0"
          y="0"
          width="260"
          height="150"
          rx="6"
          fill="var(--color-paper-card)"
          stroke="var(--color-hairline)"
          filter="url(#ws-lift)"
        />
        <rect x="0" y="0" width="260" height="150" rx="6" fill="url(#ws-grain)" opacity="0.35" />
      </g>

      <g transform="translate(60 168) rotate(2.5)">
        <rect
          x="0"
          y="0"
          width="220"
          height="14"
          rx="2"
          fill="var(--color-terracotta)"
          opacity="0.45"
        />
        {Array.from({ length: 11 }).map((_, i) => (
          <line
            key={i}
            x1={20 * (i + 1)}
            y1="2"
            x2={20 * (i + 1)}
            y2="12"
            stroke="var(--color-ink-muted)"
            strokeWidth="0.5"
            opacity="0.35"
          />
        ))}
      </g>

      <g transform="translate(110 78) rotate(-3)">
        <rect
          x="0"
          y="0"
          width="160"
          height="100"
          rx="4"
          fill="var(--color-paper-newsprint)"
          stroke="var(--color-hairline)"
          filter="url(#ws-lift)"
        />
        <path
          d="M 0 4 L 4 0 L 12 6 L 22 2 L 36 8 L 50 4 L 64 10 L 78 6 L 92 12 L 106 8 L 120 14 L 134 10 L 148 16 L 160 12 L 160 100 L 0 100 Z"
          fill="var(--color-paper-card)"
        />
        <g opacity="0.55">
          <path
            d="M 14 32 L 146 32"
            stroke="var(--color-ink-faint)"
            strokeWidth="0.6"
          />
          <path
            d="M 14 50 L 130 50"
            stroke="var(--color-ink-faint)"
            strokeWidth="0.6"
          />
          <path
            d="M 14 68 L 140 68"
            stroke="var(--color-ink-faint)"
            strokeWidth="0.6"
          />
          <path
            d="M 14 86 L 110 86"
            stroke="var(--color-ink-faint)"
            strokeWidth="0.6"
          />
        </g>
        <text
          x="14"
          y="22"
          fontFamily="JetBrains Mono, monospace"
          fontSize="9"
          fill="var(--color-ink-muted)"
          letterSpacing="0.04em"
        >
          000001
        </text>
        <path
          d="M 14 36 L 24 32 L 34 40 L 44 36 L 54 32 L 64 28 L 74 36 L 84 32 L 94 26 L 104 32 L 114 30 L 124 24 L 134 32 L 146 28"
          fill="none"
          stroke="var(--color-sage)"
          strokeWidth="1.2"
          opacity="0.75"
        />
      </g>

      <g transform="translate(0 0)">
        <foreignObject x="240" y="30" width="120" height="40">
          <div style={{ position: "relative" }}>
            <WashiTape width={120} height={28} rotation={3} />
          </div>
        </foreignObject>
      </g>

      <g transform="translate(238 32)">
        <circle
          cx="0"
          cy="0"
          r="22"
          fill="var(--color-apricot-soft)"
          opacity="0.55"
          filter="url(#ws-lift)"
        />
        <circle
          cx="0"
          cy="0"
          r="22"
          fill="none"
          stroke="var(--color-ink-muted)"
          strokeWidth="0.7"
          opacity="0.35"
        />
        <line
          x1="0"
          y1="-18"
          x2="0"
          y2="22"
          stroke="var(--color-ink-muted)"
          strokeWidth="1.4"
          strokeLinecap="round"
          opacity="0.55"
        />
        <line
          x1="0"
          y1="22"
          x2="-10"
          y2="36"
          stroke="var(--color-ink-muted)"
          strokeWidth="1.4"
          strokeLinecap="round"
          opacity="0.55"
        />
      </g>

      <g transform="translate(60 110)">
        <rect
          x="0"
          y="0"
          width="40"
          height="28"
          rx="3"
          fill="var(--color-paper-newsprint)"
          stroke="var(--color-hairline)"
          filter="url(#ws-lift)"
          transform="rotate(8)"
        />
        <line
          x1="6"
          y1="6"
          x2="32"
          y2="6"
          stroke="var(--color-ink-faint)"
          strokeWidth="0.5"
          opacity="0.6"
          transform="rotate(8)"
        />
        <line
          x1="6"
          y1="12"
          x2="28"
          y2="12"
          stroke="var(--color-ink-faint)"
          strokeWidth="0.5"
          opacity="0.6"
          transform="rotate(8)"
        />
        <line
          x1="6"
          y1="18"
          x2="30"
          y2="18"
          stroke="var(--color-ink-faint)"
          strokeWidth="0.5"
          opacity="0.6"
          transform="rotate(8)"
        />
      </g>
    </svg>
  );
}
