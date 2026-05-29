import type { RefObject } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import {
  REPORT_SECTION_LABELS,
  isSectionPlaceholder,
  orderedReportSectionKeys,
  reportSectionDomId,
  sanitizeReportSectionBody,
} from "../utils/reportMarkdown";

const MARKDOWN_COMPONENTS: Components = {
  table: ({ children, ...rest }) => (
    <div className="markdown-table-wrap">
      <table {...rest}>{children}</table>
    </div>
  ),
};

type Props = {
  reports: Record<string, string> | undefined;
  reportBodyRef?: RefObject<HTMLDivElement | null>;
};

export function ReportSections({ reports, reportBodyRef }: Props) {
  const keys = orderedReportSectionKeys(reports);

  return (
    <div ref={reportBodyRef} className="markdown-body dashboard-report-markdown">
      {keys.map((key, index) => {
        const raw = reports?.[key] ?? "";
        const body = sanitizeReportSectionBody(key, raw);
        if (!body) return null;
        const label = REPORT_SECTION_LABELS[key] ?? key.replace(/_/g, " ");
        const placeholder = isSectionPlaceholder(key, raw);
        return (
          <section
            key={key}
            id={reportSectionDomId(key)}
            className={[
              "report-section",
              index === 0 ? "report-section--first" : "",
              placeholder ? "report-section--placeholder" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-label={label}
          >
            <h2 className="report-section__title">{label}</h2>
            <div className={placeholder ? "report-section__markdown report-section__markdown--placeholder" : "report-section__markdown"}>
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                {body}
              </ReactMarkdown>
            </div>
          </section>
        );
      })}
    </div>
  );
}
