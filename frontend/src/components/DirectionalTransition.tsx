import type { ReactNode } from "react";
import { ViewTransition } from "react";

type Props = {
  children: ReactNode;
  className?: string;
};

export function DirectionalTransition({ children }: Props) {
  return (
    <ViewTransition
      enter={{ "nav-forward": "nav-forward", "nav-back": "nav-back", default: "fade-in" }}
      exit={{ "nav-forward": "nav-forward", "nav-back": "nav-back", default: "fade-out" }}
      default="none"
    >
      {children}
    </ViewTransition>
  );
}

export function FadeTransition({ children }: { children: ReactNode }) {
  return (
    <ViewTransition enter="fade-in" exit="fade-out" default="none">
      {children}
    </ViewTransition>
  );
}
