import { motion, useReducedMotion } from "motion/react";
import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

/**
 * Primary/secondary buttons: subtle press feedback via transform (GPU-friendly).
 * Defers to a plain `<button>` when disabled or when `prefers-reduced-motion` is on.
 */
export const Pressable = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement>>(
  function Pressable({ disabled, ...rest }, ref) {
    const reduce = useReducedMotion();
    if (reduce || disabled) {
      return <button ref={ref} type="button" disabled={disabled} {...rest} />;
    }
    return (
      <motion.button
        ref={ref}
        type="button"
        disabled={disabled}
        whileTap={{ scale: 0.985 }}
        transition={{ duration: 0.12, ease: EASE }}
        {...rest}
      />
    );
  }
);
