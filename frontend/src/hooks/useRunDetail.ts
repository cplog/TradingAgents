import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchHistoryRun,
  getJob,
  openJobEvents,
  type HistoryRunDetail,
  type JobStatus,
} from "../api";
import { historyRunToJobStatus } from "../utils/jobHistoryBridge";

type ProgressEvent = { ts: string; stage: string; message: string };

export function useRunDetail(runId: string | null) {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [historyDetail, setHistoryDetail] = useState<HistoryRunDetail | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const activeIdRef = useRef<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const poll = useCallback(async (id: string) => {
    try {
      const j = await getJob(id);
      if (activeIdRef.current !== id) return;
      setNotice(null);
      setJob(j);
      if (j.progress_events?.length) setEvents(j.progress_events);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (!msg.startsWith("404:")) {
        setNotice(msg);
        return;
      }
      if (activeIdRef.current !== id) return;
      try {
        const persisted = await fetchHistoryRun(id);
        if (activeIdRef.current !== id) return;
        setHistoryDetail(persisted);
        setJob(historyRunToJobStatus(persisted));
        setNotice("Loaded from History (job no longer in the live worker queue).");
      } catch {
        setJob(null);
        setHistoryDetail(null);
        setNotice("Run not found in the worker queue or History.");
      }
    }
  }, []);

  useEffect(() => {
    const id = runId?.trim();
    if (!id) {
      activeIdRef.current = null;
      setJob(null);
      setHistoryDetail(null);
      setEvents([]);
      setNotice(null);
      return;
    }
    let cancelled = false;
    activeIdRef.current = id;
    setLoading(true);
    setNotice(null);
    const nowIso = new Date().toISOString();
    setJob({
      job_id: id,
      status: "running",
      created_at: nowIso,
      ticker: null,
      date: null,
      result: null,
      error: null,
      progress_events: [{ ts: nowIso, stage: "running", message: "Loading run…" }],
      batch_id: null,
    });
    setEvents([{ ts: nowIso, stage: "running", message: "Loading run…" }]);

    void (async () => {
      await poll(id);
      if (!cancelled) setLoading(false);
    })();

    return () => {
      cancelled = true;
      esRef.current?.close();
    };
  }, [runId, poll]);

  useEffect(() => {
    const id = runId?.trim();
    if (!id) return;
    if (job?.status && job.status !== "queued" && job.status !== "running" && job.status !== "resuming") {
      return;
    }
    poll(id);
    const t = setInterval(() => poll(id), 4000);
    return () => clearInterval(t);
  }, [runId, job?.status, poll]);

  useEffect(() => {
    const id = runId?.trim();
    if (!id) return;
    if (job?.status && job.status !== "queued" && job.status !== "running" && job.status !== "resuming") {
      esRef.current?.close();
      return;
    }
    esRef.current?.close();
    const es = openJobEvents(id);
    esRef.current = es;
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "terminal") {
          void poll(id);
          es.close();
        } else if (data.message) {
          setEvents((prev) => [...prev, data]);
        }
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [runId, job?.status, poll]);

  const jobActive =
    job?.status === "queued" || job?.status === "running" || job?.status === "resuming";

  return {
    job,
    historyDetail,
    events,
    notice,
    loading,
    jobActive,
    refresh: () => {
      const id = runId?.trim();
      if (id) void poll(id);
    },
  };
}
