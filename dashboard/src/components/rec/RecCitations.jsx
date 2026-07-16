import { bucketColor, bucketLabel, pctLabel, urlLabel } from "../../lib/recview";
import InfoTip from "../InfoTip";

// Ranked "what AI cites" panel from the router's winner summary: domain
// (linked), source-type chip, citation-count bar. Abstaining pages
// (source_type "other") render dimmed with their abstention reason on hover.
export default function RecCitations({ router, title }) {
  const winners = router?.winners || [];
  if (!winners.length) return null;
  const reasons = Object.fromEntries((router.abstentions || []).map((a) => [a.url, a.reason]));
  const max = Math.max(...winners.map((w) => w.citation_count || 0), 1);
  return (
    <div>
      <p className="rc-pane__title">
        {title ?? "What AI cites for this question"}
        <InfoTip id="citations_panel" />
      </p>
      <div className="rc-cites">
        {winners.map((w) => {
          const abstained = w.source_type === "other";
          return (
            <div className={`rc-cite${abstained ? " rc-cite--dim" : ""}`} key={w.url}>
              <span className="rc-cite__domain">
                <a href={w.url} target="_blank" rel="noreferrer">{urlLabel(w.url)}</a>
              </span>
              <span
                className="rc-cite__type"
                title={abstained ? `abstained: ${reasons[w.url] ?? "no classification"}` : w.page_type ?? undefined}
              >
                <i className="rc-dot" style={{ background: bucketColor(w.source_type) }} />
                {bucketLabel(w.source_type)}
              </span>
              <span className="rc-cite__bar">
                <i style={{ "--w": `${((w.citation_count || 0) / max) * 100}%` }} />
              </span>
              <span className="rc-cite__n">{w.citation_count}×</span>
            </div>
          );
        })}
      </div>
      {router.qc_share != null && (
        <p className="rc-cites__qcnote">
          QC is cited in {pctLabel(router.qc_share)} of responses for this question.
          <InfoTip id="losing_question" />
        </p>
      )}
    </div>
  );
}
