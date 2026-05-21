import { DashboardPage } from "./DashboardPage";

/**
 * `/runs/:jobId` renders the same DashboardPage as `/dashboard`, but with the
 * configuration form hidden and the focus shifted to live run + results. The
 * page reads `:jobId` from the URL params and treats it the same as the legacy
 * `/dashboard?job=` deep-link.
 */
export function RunJobPage() {
  return <DashboardPage />;
}
