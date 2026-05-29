import { useCallback, useEffect, useState } from "react";
import { getHistoryRunLiveContext, getJobLiveContext } from "../api";
import type { JobLiveContext } from "../utils/livePlanContext";

export function useLivePlanContext(runId: string, enabled: boolean) {
  const [context, setContext] = useState<JobLiveContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!runId.trim() || !enabled) {
      setContext(null);
      setError(null);
      return;
    }
    setLoading(true);
    try {
      let data: JobLiveContext;
      try {
        data = await getJobLiveContext(runId);
      } catch {
        data = await getHistoryRunLiveContext(runId);
      }
      setContext(data);
      setError(null);
    } catch (e: unknown) {
      setContext(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [runId, enabled]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { context, loading, error, refresh };
}
