import { AnimatePresence, motion } from "motion/react";
import { Link, NavLink, Outlet, useLocation, useMatch } from "react-router-dom";
import { useRouteTransitionMotion } from "../hooks/useRouteTransitionMotion";
import { JobsRibbon } from "./JobsRibbon";
import { JobsTrackerProvider } from "../contexts/JobsTrackerContext";
import { isRunsWorkflowPath, paths } from "../navigation/routes";

type NavItem = {
  to: string;
  label: string;
  hint?: string;
  /** NavLink `end` — exact pathname match only when true. */
  end?: boolean;
  /** Also mark active when pathname starts with any of these prefixes. */
  activePrefixes?: string[];
};

const navGroups: { label: string; items: NavItem[] }[] = [
  {
    label: "Start",
    items: [
      {
        to: paths.dashboard,
        label: "Analysis",
        hint: "Single-stock run",
        end: true,
      },
      {
        to: paths.batch,
        label: "Batch",
        hint: "Many tickers at once",
        end: true,
      },
    ],
  },
  {
    label: "Review",
    items: [
      {
        to: paths.history,
        label: "Runs",
        hint: "Index, compare, stats, open reports",
        end: true,
        activePrefixes: ["/runs/", "/stocks/", "/history/"],
      },
    ],
  },
  {
    label: "Research",
    items: [
      { to: paths.screener, label: "Screener", hint: "Facts-only screen", end: true },
      { to: paths.sectors, label: "Sectors", hint: "Industry rollups", end: true },
      { to: paths.news, label: "News", hint: "Headlines feed", end: true },
      { to: paths.topics, label: "Topics", hint: "Hot ideas & themes", end: true },
      { to: paths.watchlists, label: "Watchlists", hint: "Browser shortcuts", end: true },
      { to: paths.monitor, label: "Monitor", hint: "Overnight auto-scan", end: true },
    ],
  },
  {
    label: "System",
    items: [
      { to: paths.system, label: "System", hint: "API, health, external consoles", end: true },
    ],
  },
];

function navLinkClass(isActive: boolean): string {
  return `app-shell__nav-link${isActive ? " app-shell__nav-link--active" : ""}`;
}

function isNavItemActive(
  pathname: string,
  to: string,
  end?: boolean,
  activePrefixes?: string[],
): boolean {
  if (activePrefixes?.some((p) => pathname.startsWith(p))) return true;
  if (end) return pathname === to;
  return pathname === to || pathname.startsWith(`${to}/`);
}

function SidebarContext() {
  const runMatch = useMatch("/runs/:jobId");
  const stockMatch = useMatch("/stocks/:ticker");
  const runId = runMatch?.params.jobId?.trim();
  const ticker = stockMatch?.params.ticker?.trim().toUpperCase();

  if (!runId && !ticker) return null;

  return (
    <section className="app-shell__context" aria-label="Current context">
      <div className="app-shell__context-label">You are here</div>
      {runId ? (
        <div className="app-shell__context-body">
          <div className="app-shell__context-title">Run report</div>
          <div className="app-shell__context-meta mono" title={runId}>
            {runId.length > 28 ? `${runId.slice(0, 14)}…${runId.slice(-10)}` : runId}
          </div>
        </div>
      ) : null}
      {ticker ? (
        <div className="app-shell__context-body">
          <div className="app-shell__context-title mono">{ticker}</div>
          <div className="app-shell__context-meta">Stock-level history</div>
        </div>
      ) : null}
    </section>
  );
}

export function Layout() {
  const location = useLocation();
  const routeMotion = useRouteTransitionMotion();
  const pathname = location.pathname;
  const inRunsWorkflow = isRunsWorkflowPath(pathname);

  return (
    <JobsTrackerProvider>
    <div className="app-shell">
      <aside className="app-shell__nav" aria-label="Application navigation">
        <Link to={paths.dashboard} className="app-shell__brand">
          <div className="app-shell__brand-title">TradingAgents</div>
          <div className="app-shell__brand-sub">Command center</div>
        </Link>

        {navGroups.map((group) => (
          <div key={group.label} className="app-shell__nav-group">
            <div className="app-shell__nav-group-label">{group.label}</div>
            <nav className="app-shell__nav-links" aria-label={group.label}>
              {group.items.map(({ to, label, hint, end, activePrefixes }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={navLinkClass(
                    isNavItemActive(pathname, to, end, activePrefixes),
                  )}
                  aria-current={
                    isNavItemActive(pathname, to, end, activePrefixes) ? "page" : undefined
                  }
                >
                  <span className="app-shell__nav-link-label">{label}</span>
                  {hint ? <span className="app-shell__nav-link-hint">{hint}</span> : null}
                </NavLink>
              ))}
            </nav>
          </div>
        ))}

        <SidebarContext />

        {inRunsWorkflow ? (
          <p className="app-shell__nav-footnote">
            Reports live on <strong>Run</strong> pages. This sidebar stays on the index while you read output.
          </p>
        ) : null}
      </aside>

      <div className="app-shell__content">
        <div className="app-shell__status" role="status" aria-live="polite">
          <span className="app-shell__status-dot" aria-hidden />
          <span className="app-shell__status-text">Research terminal · retro digital</span>
        </div>
        <JobsRibbon />
        <main className="app-shell__main" id="main-content">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={location.pathname} {...routeMotion} className="app-shell__page">
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
    </JobsTrackerProvider>
  );
}
