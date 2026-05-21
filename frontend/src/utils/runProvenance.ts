import type { RunProvenance } from "../api";

export function formatLlmLabel(prov: RunProvenance | null | undefined): string {
  if (!prov?.llm_provider) return "—";
  const deep = prov.llm_deep?.trim();
  const quick = prov.llm_quick?.trim();
  if (deep && quick && deep !== quick) {
    return `${prov.llm_provider} · ${truncate(deep)} / ${truncate(quick)}`;
  }
  if (deep) return `${prov.llm_provider} · ${truncate(deep)}`;
  return prov.llm_provider;
}

export function formatSourcesLabel(prov: RunProvenance | null | undefined): string {
  if (!prov) return "—";
  const pillars = prov.source_pillars ?? 0;
  const vendors = prov.vendor_count ?? 0;
  const analysts = prov.analysts_total ?? 0;
  const parts: string[] = [];
  if (pillars > 0) {
    parts.push(`${pillars}/4 pillars`);
  }
  if (vendors === 1) {
    parts.push("1 vendor");
  } else if (vendors > 1) {
    parts.push(`${vendors} vendors`);
  }
  if (analysts > 0) {
    const ok = prov.analysts_ok ?? 0;
    const empty = prov.analysts_empty ?? 0;
    if (ok > 0 || empty > 0) {
      parts.push(`${analysts} analysts (${ok} ok${empty ? `, ${empty} empty` : ""})`);
    } else {
      parts.push(`${analysts} analysts`);
    }
  }
  if (parts.length === 0 && prov.data_routing) {
    return truncate(prov.data_routing, 48);
  }
  return parts.length ? parts.join(" · ") : "—";
}

export function provenanceTitle(prov: RunProvenance | null | undefined): string {
  if (!prov) return "No provenance recorded for this run.";
  const lines = [
    `LLM: ${formatLlmLabel(prov)}`,
    prov.data_routing ? `Data: ${prov.data_routing}` : "",
    prov.analysts_selected?.length
      ? `Analysts: ${prov.analysts_selected.join(", ")}`
      : "",
    ...(prov.bias_warnings ?? []).map((w) => `⚠ ${w}`),
  ].filter(Boolean);
  return lines.join("\n");
}

export function hasBiasWarning(prov: RunProvenance | null | undefined): boolean {
  return Boolean(prov?.bias_warnings?.length);
}

function truncate(s: string, max = 22): string {
  const t = s.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}
