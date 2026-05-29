import { createContext, useContext, type ReactNode } from "react";
import { useJobsTracker, type JobsTracker } from "../hooks/useJobsTracker";

const JobsTrackerContext = createContext<JobsTracker | null>(null);

/** Single app-wide jobs poll for the status bar (shared with submit flows). */
export function JobsTrackerProvider({ children }: { children: ReactNode }) {
  const tracker = useJobsTracker();
  return (
    <JobsTrackerContext.Provider value={tracker}>{children}</JobsTrackerContext.Provider>
  );
}

export function useJobsTrackerContext(): JobsTracker {
  const ctx = useContext(JobsTrackerContext);
  if (!ctx) {
    throw new Error("useJobsTrackerContext must be used within JobsTrackerProvider");
  }
  return ctx;
}

/** Call after POST /analyze or /batches so the ribbon picks up the new job immediately. */
export function useJobsRefresh(): () => void {
  const ctx = useContext(JobsTrackerContext);
  return ctx?.refresh ?? (() => {});
}
