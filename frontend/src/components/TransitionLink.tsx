import { startTransition } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import type { LinkProps, NavLinkProps } from "react-router-dom";

export function useTransitionNavigate() {
  const navigate = useNavigate();
  return (to: string) => {
    startTransition(() => {
      navigate(to);
    });
  };
}

function TransitionLinkInner({ to, direction = "nav-forward", onClick, children, ...props }: LinkProps & { direction?: "nav-forward" | "nav-back" }) {
  const navigate = useNavigate();
  return (
    <Link
      to={to}
      onClick={(e) => {
        onClick?.(e);
        if (!e.defaultPrevented) {
          e.preventDefault();
          startTransition(() => {
            (document as unknown as { addTransitionType?: (t: string) => void })
              .addTransitionType?.(direction);
            navigate(to);
          });
        }
      }}
      {...props}
    >
      {children}
    </Link>
  );
}

function TransitionNavLinkInner({ to, direction = "nav-forward", onClick, children, ...props }: NavLinkProps & { direction?: "nav-forward" | "nav-back" }) {
  const navigate = useNavigate();
  return (
    <NavLink
      to={to}
      onClick={(e) => {
        onClick?.(e);
        if (!e.defaultPrevented) {
          e.preventDefault();
          startTransition(() => {
            (document as unknown as { addTransitionType?: (t: string) => void })
              .addTransitionType?.(direction);
            navigate(to);
          });
        }
      }}
      {...props}
    >
      {children}
    </NavLink>
  );
}

export { TransitionLinkInner as TransitionLink, TransitionNavLinkInner as TransitionNavLink };
