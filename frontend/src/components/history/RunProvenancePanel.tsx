import type { RunProvenance } from "../../api";
import {
  formatLlmLabel,
  formatSourcesLabel,
  provenanceTitle,
} from "../../utils/runProvenance";

type RunProvenancePanelProps = {
  provenance: RunProvenance | null | undefined;
  compact?: boolean;
};

export function RunProvenancePanel({ provenance, compact = false }: RunProvenancePanelProps) {
  if (!provenance) {
    return (
      <p className="run-provenance run-provenance--empty">
        No model or data-source snapshot for this run (older runs may lack provenance). Compare ratings only
        after confirming the same LLM and vendor setup.
      </p>
    );
  }

  const warnings = provenance.bias_warnings ?? [];

  if (compact) {
    return (
      <div className="run-provenance run-provenance--compact" title={provenanceTitle(provenance)}>
        <span className="run-provenance__chip run-provenance__chip--llm">{formatLlmLabel(provenance)}</span>
        <span
          className={`run-provenance__chip run-provenance__chip--sources${
            warnings.length ? " run-provenance__chip--warn" : ""
          }`}
        >
          {formatSourcesLabel(provenance)}
        </span>
      </div>
    );
  }

  return (
    <section className="run-provenance" aria-label="Run provenance">
      <p className="run-provenance__lead">
        Model and data setup for this run. Compare History rows only when these match, or bias can dominate
        the rating difference.
      </p>
      <dl className="run-provenance__grid">
        <div>
          <dt>LLM</dt>
          <dd>{formatLlmLabel(provenance)}</dd>
        </div>
        <div>
          <dt>Data routing</dt>
          <dd>{provenance.data_routing ?? "—"}</dd>
        </div>
        <div>
          <dt>Analysts</dt>
          <dd>
            {provenance.analysts_selected?.length
              ? provenance.analysts_selected.join(", ")
              : provenance.analysts_total
                ? `${provenance.analysts_total} selected`
                : "—"}
            {provenance.analysts_ok != null && provenance.analysts_total ? (
              <span className="run-provenance__sub">
                {" "}
                · {provenance.analysts_ok} ok
                {provenance.analysts_empty ? ` · ${provenance.analysts_empty} empty` : ""}
              </span>
            ) : null}
          </dd>
        </div>
        <div>
          <dt>Source diversity</dt>
          <dd>
            {provenance.source_pillars ?? 0}/4 pillars · {provenance.vendor_count ?? 0} vendor
            {(provenance.vendor_count ?? 0) === 1 ? " (single-source)" : "s"}
          </dd>
        </div>
      </dl>
      {warnings.length > 0 && (
        <ul className="run-provenance__warnings">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
