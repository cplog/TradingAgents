import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, type CSSProperties } from "react";
import * as THREE from "three";

type SheetSpec = {
  position: [number, number, number];
  rotation: [number, number, number];
  color: string;
  size: [number, number];
};

const SHEETS: SheetSpec[] = [
  { position: [-0.04, -0.08, -0.05], rotation: [0, 0.06, 0], color: "#ede4d3", size: [1.7, 1.15] },
  { position: [0.03, -0.03, -0.02], rotation: [0, -0.05, 0], color: "#f4ece0", size: [1.65, 1.1] },
  { position: [-0.02, 0.02, 0.01], rotation: [0, 0.03, 0], color: "#fffbf3", size: [1.6, 1.08] },
  { position: [0.02, 0.07, 0.04], rotation: [0, -0.04, 0.01], color: "#faf6f0", size: [1.55, 1.05] },
];

function PaperSheet({ spec, index }: { spec: SheetSpec; index: number }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const baseRotY = spec.rotation[1];
  const baseY = spec.position[1];
  useFrame((state) => {
    if (!meshRef.current) return;
    const t = state.clock.elapsedTime;
    meshRef.current.rotation.y = baseRotY + Math.sin(t * 0.25 + index * 0.6) * 0.045;
    meshRef.current.rotation.x = spec.rotation[0] + Math.cos(t * 0.2 + index) * 0.015;
    meshRef.current.position.y = baseY + Math.sin(t * 0.45 + index * 0.4) * 0.018;
  });
  return (
    <mesh ref={meshRef} position={spec.position} rotation={spec.rotation}>
      <planeGeometry args={spec.size} />
      <meshStandardMaterial
        color={spec.color}
        roughness={0.94}
        metalness={0}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

function Stack() {
  return (
    <group>
      {SHEETS.map((s, i) => (
        <PaperSheet key={i} spec={s} index={i} />
      ))}
    </group>
  );
}

function DemandTicker({ active }: { active: boolean }) {
  const { invalidate } = useThree();
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      if (now - last >= 33) {
        last = now;
        invalidate();
      }
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [active, invalidate]);
  return null;
}

export type PaperStackSceneProps = {
  className?: string;
  style?: CSSProperties;
  width?: number | string;
  height?: number | string;
};

export function PaperStackScene({
  className,
  style,
  width = "100%",
  height = 240,
}: PaperStackSceneProps) {
  const containerStyle = useMemo<CSSProperties>(
    () => ({
      width,
      height: typeof height === "number" ? `${height}px` : height,
      ...style,
    }),
    [width, height, style],
  );
  const reducedMotion = useMemo(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }, []);
  return (
    <div className={className} style={containerStyle} aria-hidden="true">
      <Canvas
        camera={{ position: [0, 0.4, 2.6], fov: 32 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
        frameloop={reducedMotion ? "never" : "demand"}
        style={{ background: "transparent" }}
      >
        <ambientLight intensity={0.55} color="#fff4e3" />
        <directionalLight position={[2.5, 3, 2]} intensity={0.95} color="#fff4e3" />
        <directionalLight position={[-2, 1, 1.5]} intensity={0.45} color="#f4b888" />
        <directionalLight position={[0, -1, 1]} intensity={0.18} color="#ede4d3" />
        <Stack />
        <DemandTicker active={!reducedMotion} />
      </Canvas>
    </div>
  );
}
