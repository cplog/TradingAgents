import { useReducedMotion } from "motion/react";
import type { HTMLMotionProps } from "motion/react";

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

/**
 * Route outlet cross-fade + short vertical drift.
 * Disabled when `prefers-reduced-motion` is set (instant swap).
 */
export function useRouteTransitionMotion(): Pick<
  HTMLMotionProps<"div">,
  "initial" | "animate" | "exit" | "transition"
> {
  const reduce = useReducedMotion();
  if (reduce) {
    return {
      initial: false,
      animate: { opacity: 1 },
      exit: { opacity: 1 },
      transition: { duration: 0 },
    };
  }
  return {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -8, transition: { duration: 0.16, ease: EASE } },
    transition: { duration: 0.24, ease: EASE },
  };
}
