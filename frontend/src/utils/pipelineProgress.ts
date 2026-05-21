/** Infer pipeline node states from job status + progress_events. */

export type PipelineNodeId =
  | "queued"
  | "analysts"
  | "graph"
  | "dimensions"
  | "report"
  | "done";

export type PipelineNodeState = "pending" | "running" | "done" | "failed";

export type PipelineNodeRow = {
  id: PipelineNodeId;
  label: string;
  state: PipelineNodeState;
  elapsedSec: number | null;
  detail: string | null;
};

export type ProgressEvent = {
  ts: string;
  stage: string;
  message: string;
  details?: string;
};

const NODE_ORDER: PipelineNodeId[] = [
  "queued",
  "analysts",
  "graph",
  "dimensions",
  "report",
  "done",
];

const NODE_LABELS: Record<PipelineNodeId, string> = {
  queued: "Queued",
  analysts: "Analyst team",
  graph: "Research & risk debate",
  dimensions: "Dimensional study",
  report: "Report assembly",
  done: "Complete",
};

function parseTs(ts: string | undefined): number {
  if (!ts) return 0;
  const t = Date.parse(ts);
  return Number.isFinite(t) ? t : 0;
}

function classifyEvent(message: string, stage: string): PipelineNodeId | null {
  const m = message.toLowerCase();
  const s = stage.toLowerCase();
  if (s === "queued" || m.includes("queued for")) return "queued";
  if (s === "completed" || m.includes("analysis complete")) return "done";
  if (s === "failed" || s === "cancelled") return null;
  if (s === "dimensions" || m.includes("building dimensions")) return "dimensions";
  if (m.includes("building report")) return "report";
  if (
    m.includes("langgraph") ||
    m.includes("still in langgraph") ||
    m.includes("debate") ||
    m.includes("research manager") ||
    m.includes("portfolio manager") ||
    m.includes("trader")
  ) {
    return "graph";
  }
  if (
    m.includes("parallel analyst") ||
    m.includes("analyst nodes") ||
    m.includes("market analyst") ||
    m.includes("news analyst") ||
    m.includes("sentiment") ||
    m.includes("fundamentals")
  ) {
    return "analysts";
  }
  if (m.includes("starting multi-agent")) return "analysts";
  return null;
}

function maxReachedNode(events: ProgressEvent[]): PipelineNodeId {
  let maxIdx = 0;
  for (const e of events) {
    const node = classifyEvent(e.message, e.stage);
    if (!node) continue;
    const idx = NODE_ORDER.indexOf(node);
    if (idx >= 0 && idx > maxIdx) maxIdx = idx;
  }
  return NODE_ORDER[maxIdx] ?? "queued";
}

function stateForIndex(
  index: number,
  activeIndex: number,
  jobStatus: string
): PipelineNodeState {
  if (jobStatus === "failed") {
    if (index < activeIndex) return "done";
    if (index === activeIndex) return "failed";
    return "pending";
  }
  if (jobStatus === "completed") return "done";
  if (index < activeIndex) return "done";
  if (index === activeIndex) {
    if (jobStatus === "queued" && activeIndex === 0) return "running";
    if (jobStatus === "running" || jobStatus === "resuming") return "running";
    return "pending";
  }
  return "pending";
}

function detailForNode(
  id: PipelineNodeId,
  events: ProgressEvent[],
  lastGraphStep: number | null | undefined
): string | null {
  const relevant = [...events].reverse();
  for (const e of relevant) {
    const node = classifyEvent(e.message, e.stage);
    if (node === id) {
      const msg = e.message.trim();
      if (msg.length > 120) return `${msg.slice(0, 117)}…`;
      return msg;
    }
  }
  if (id === "graph" && lastGraphStep != null) {
    return `Checkpoint step ${lastGraphStep}`;
  }
  return null;
}

function elapsedForNode(
  id: PipelineNodeId,
  events: ProgressEvent[],
  jobCreatedAt: string | undefined,
  nowMs: number
): number | null {
  const nodeIdx = NODE_ORDER.indexOf(id);
  let started: number | null = null;
  let ended: number | null = null;

  for (const e of events) {
    const node = classifyEvent(e.message, e.stage);
    if (!node) continue;
    const idx = NODE_ORDER.indexOf(node);
    const ts = parseTs(e.ts);
    if (idx === nodeIdx && started == null) started = ts || started;
    if (idx > nodeIdx && started != null && ended == null) ended = ts || ended;
  }

  if (started == null && nodeIdx === 0 && jobCreatedAt) {
    started = parseTs(jobCreatedAt);
  }

  if (started == null) return null;
  const end = ended ?? nowMs;
  const sec = Math.floor((end - started) / 1000);
  return sec >= 0 ? sec : null;
}

export function buildPipelineNodeRows(
  jobStatus: string,
  events: ProgressEvent[],
  options?: {
    createdAt?: string;
    lastGraphStep?: number | null;
    nowMs?: number;
  }
): PipelineNodeRow[] {
  const status = jobStatus.toLowerCase();
  const nowMs = options?.nowMs ?? Date.now();
  const reached = maxReachedNode(events);
  let activeIndex = NODE_ORDER.indexOf(reached);
  if (status === "completed") activeIndex = NODE_ORDER.length - 1;
  if (status === "queued") activeIndex = 0;
  if (status === "failed") {
    activeIndex = Math.min(activeIndex, NODE_ORDER.length - 2);
  }

  return NODE_ORDER.map((id, index) => ({
    id,
    label: NODE_LABELS[id],
    state: stateForIndex(index, activeIndex, status),
    elapsedSec: elapsedForNode(id, events, options?.createdAt, nowMs),
    detail: detailForNode(id, events, options?.lastGraphStep),
  }));
}

export function formatPipelineElapsed(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}
