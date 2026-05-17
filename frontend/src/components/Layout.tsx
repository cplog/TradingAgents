import { AnimatePresence, motion } from "motion/react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useRouteTransitionMotion } from "../hooks/useRouteTransitionMotion";

const nav: { to: string; label: string }[] = [
  { to: "/dashboard", label: "Analysis" },
  { to: "/history", label: "History" },
  { to: "/batch", label: "Batch" },
  { to: "/screener", label: "Screener" },
  { to: "/sectors", label: "Sectors" },
  { to: "/news", label: "News" },
  { to: "/system", label: "System" },
  { to: "/admin", label: "Admin links" },
];

const navEase = "cubic-bezier(0.22, 1, 0.36, 1)";

export function Layout() {
  const location = useLocation();
  const routeMotion = useRouteTransitionMotion();

  return (
    <div className="app-shell">
      <aside
        className="app-shell__nav"
        style={{
          background: "var(--surface-cloud-white)",
          borderRight: "1px solid var(--color-stone-border)",
          padding: "var(--spacing-24) var(--spacing-16)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--spacing-8)",
        }}
      >
        <div style={{ marginBottom: "var(--spacing-16)" }}>
          <div
            style={{
              fontFamily: "var(--font-roobert), var(--font-inter)",
              fontSize: "var(--text-heading-sm)",
              fontWeight: 600,
            }}
          >
            TradingAgents
          </div>
          <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
            Command center
          </div>
        </div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {nav.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              style={({ isActive }) => ({
                padding: "var(--spacing-8) var(--spacing-12)",
                borderRadius: "var(--radius-md)",
                color: isActive ? "var(--color-chartwell-blue)" : "var(--color-slate-text)",
                background: isActive ? "var(--color-sky-tint)" : "transparent",
                fontWeight: isActive ? 600 : 500,
                textDecoration: "none",
                transition: `background-color 0.2s ${navEase}, color 0.2s ${navEase}, font-weight 0s`,
              })}
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main
        className="app-shell__main"
        style={{
          padding: "var(--spacing-32)",
        }}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={location.pathname}
            {...routeMotion}
            style={{ minHeight: "100%" }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
