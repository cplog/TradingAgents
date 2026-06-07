import { useEffect, useId, useRef } from "react";
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

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

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
  const titleId = useId();
  const descId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const returnFocusRef = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusInitial = () => {
      const node = dialogRef.current;
      if (!node) return;
      const focusables = node.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      const first = focusables[0];
      (first ?? node).focus();
    };

    const focusTimer = window.setTimeout(focusInitial, 0);

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        if (!submitting) onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const node = dialogRef.current;
      if (!node) return;
      const focusables = Array.from(
        node.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => !el.hasAttribute("aria-hidden"));
      if (focusables.length === 0) {
        e.preventDefault();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && (active === first || !node.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKey, true);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", handleKey, true);
      document.body.style.overflow = previousOverflow;
      const returnTo = returnFocusRef.current;
      if (returnTo instanceof HTMLElement) {
        returnTo.focus();
      }
    };
  }, [open, submitting, onClose]);

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
        aria-labelledby={titleId}
        aria-describedby={descId}
        ref={dialogRef}
        tabIndex={-1}
      >
        <header className="rerun-setup-dialog__head">
          <h2 id={titleId} className="rerun-setup-dialog__title">
            {title}
          </h2>
          <p id={descId} className="rerun-setup-dialog__desc">
            {description}
          </p>
          {runSummary ? (
            <p className="rerun-setup-dialog__meta">
              <strong>Run:</strong> {runSummary}
            </p>
          ) : null}
          {priorRunLlm ? (
            <p className="rerun-setup-dialog__meta">
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
        </header>

        <div className="rerun-setup-dialog__body">
          <div className="rerun-setup-dialog__picker">
            <LlmPicker
              value={config}
              onChange={setConfig}
              onReset={reset}
              disabled={submitting}
              variant="full"
            />
          </div>
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
