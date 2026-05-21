/**
 * Shared export toolbar for completed agent reports (HTML, print/PDF, markdown).
 */

type ReportExportBarProps = {
  onExportHtml: () => void;
  onPrint: () => void;
  markdownHref: string | null;
  disabled?: boolean;
  disabledHint?: string;
  /** Pins the bar under the app header while scrolling long reports. */
  sticky?: boolean;
  className?: string;
};

export function ReportExportBar({
  onExportHtml,
  onPrint,
  markdownHref,
  disabled = false,
  disabledHint,
  sticky = false,
  className = "",
}: ReportExportBarProps) {
  const rootClass = [
    "report-export-bar",
    sticky ? "report-export-bar--sticky" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClass} role="toolbar" aria-label="Export report">
      <div className="report-export-bar__lead">
        <span className="report-export-bar__title">Export report</span>
        <span className="report-export-bar__hint">
          {disabled && disabledHint
            ? disabledHint
            : "HTML archive · browser PDF · raw markdown"}
        </span>
      </div>
      <div className="report-export-bar__actions">
        <button
          type="button"
          className="ui-btn-secondary"
          onClick={onExportHtml}
          disabled={disabled}
          title="Download a self-contained HTML file (summary + full report)."
        >
          HTML
        </button>
        <button
          type="button"
          className="ui-btn-secondary"
          onClick={onPrint}
          disabled={disabled}
          title="Open the browser print dialog. Choose Save as PDF for a printable report."
        >
          Print / PDF
        </button>
        {markdownHref ? (
          <a
            href={markdownHref}
            className="ui-btn-secondary report-export-bar__link"
            title="Raw markdown source from the API."
            download
          >
            Markdown
          </a>
        ) : (
          <button type="button" className="ui-btn-secondary" disabled title="No job id for markdown export.">
            Markdown
          </button>
        )}
      </div>
    </div>
  );
}
