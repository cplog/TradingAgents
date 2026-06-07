import { describe, expect, it } from "vitest";
import { buildPipelineNodeRows } from "./pipelineProgress";

describe("buildPipelineNodeRows", () => {
  it("marks completed job as all done", () => {
    const rows = buildPipelineNodeRows("completed", [
      { ts: "2026-05-20T10:00:00Z", stage: "queued", message: "Job abc queued for AAPL" },
      { ts: "2026-05-20T10:01:00Z", stage: "running", message: "Parallel analyst nodes: market" },
      { ts: "2026-05-20T10:03:00Z", stage: "running", message: "Still in LangGraph (~120s elapsed)" },
      { ts: "2026-05-20T10:04:00Z", stage: "dimensions", message: "Building dimensions: scoring" },
      { ts: "2026-05-20T10:05:00Z", stage: "running", message: "Building report artifact …" },
      { ts: "2026-05-20T10:05:30Z", stage: "completed", message: "Analysis complete." },
    ]);
    expect(rows.every((r) => r.state === "done")).toBe(true);
  });

  it("classifies completed node progress as graph stage", () => {
    const rows = buildPipelineNodeRows(
      "running",
      [
        { ts: "2026-05-20T10:00:00Z", stage: "queued", message: "Job queued" },
        { ts: "2026-05-20T10:00:10Z", stage: "running", message: "Completed node: Market Analyst" },
      ],
      { nowMs: Date.parse("2026-05-20T10:02:00Z") }
    );
    const graph = rows.find((r) => r.id === "graph");
    expect(graph?.state).toBe("running");
    expect(graph?.detail).toMatch(/Completed node: Market Analyst/);
  });
});
