import { useEffect, useRef } from "react";
import {
  LlmPicker,
  useLlmConfig,
  type LlmConfig,
} from "./LlmPicker";
import { llmConfigFromSnapshot } from "../utils/historyRerun";

export type RerunSetupDialogProps = {
  open: boolean;
  title: string;
  description: string;
  /** e.g. "MNSO · 2026-05-25" */
  runSummary?: string | null;
  /** e.g. "openai · gpt-5.4 / gpt-5.4-mini" */
  priorRunLlm?: string | null;
  configSnapshot?: Record<string, unknown> | null;
  submitting?: boolean;
  confirmLabel?: string;
  onClose: () => void;
  onConfirm: (llm: LlmConfig) => void | Promise<void>;
};

export function RerunSetupDialog({
  open,
  title,
  description,
  runSummary,
  priorRunLlm,
  configSnapshot,
  submitting = false,
  confirmLabel = "Start run",
  onClose,
  onConfirm,
}: RerunSetupDialogProps) {
  const { config, setConfig, reset } = useLlmConfig();
  const openedRef = useRef(false);

  useEffect(() => {
    if (!open) {
      openedRef.current = false;
      return;
    }
    if (openedRef.current) return;
    openedRef.current = true;
  }, [open]);

  if (!open) return null;

  function copyFromPreviousRun() {
    const partial = llmConfigFromSnapshot(configSnapshot);
    if (Object.keys(partial).length) setConfig(partial);
  }

  return (
    <div
      className="rerun-setup-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div
        className="rerun-setup-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rerun-setup-title"
      >
        <h2 id="rerun-setup-title" className="rerun-setup-dialog__title">
          {title}
        </h2>
        <p className="rerun-setup-dialog__desc">{description}</p>
        {runSummary ? (
          <p className="rerun-setup-dialog__meta">
            <strong>Run:</strong> {runSummary}
          </p>
        ) : null}
        {priorRunLlm ? (
          <p className="rerun-setup-dialog__meta ui-muted">
            Previous run used: {priorRunLlm}
            {configSnapshot && Object.keys(llmConfigFromSnapshot(configSnapshot)).length > 0 ? (
              <>
                {" "}
                <button
                  type="button"
                  className="rerun-setup-dialog__link"
                  disabled={submitting}
                  onClick={copyFromPreviousRun}
                >
                  Copy into picker
                </button>
              </>
            ) : null}
          </p>
        ) : null}

        <div className="rerun-setup-dialog__picker">
          <LlmPicker
            value={config}
            onChange={setConfig}
            onReset={reset}
            disabled={submitting}
            variant="full"
          />
        </div>

        <div className="rerun-setup-dialog__actions">
          <button
            type="button"
            className="ui-btn-secondary"
            disabled={submitting}
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="ui-btn ui-btn--primary"
            disabled={submitting}
            onClick={() => void onConfirm(config)}
          >
            {submitting ? "Submitting…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
