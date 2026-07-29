import { bucketColor, bucketLabel, pctLabel, urlLabel } from "../../lib/recview";
import InfoTip from "../InfoTip";

// Ranked "what AI cites" panel. Pass `sc` (the fix card's scorecard) to show
// EVERY cited page that fed the "Compared against · N of M cited pages"
// title - analyzed winners, unreadable ones, and not-comparable ones alike -
// instead of just router.winners, which is a smaller, differently-sized top-5
// sample from the routing vote (route["winners"]), not the scorecard's fuller
// pool. Without `sc` (reach/build cards, which have no scorecard), falls back
// to that router sample as before.
export default function RecCitations({ router, sc, title }) {
  const rows = sc
    ? [...(sc.winners || []), ...(sc.winners_unreadable || []), ...(sc.winners_excluded || [])]
        .sort((a, b) => (b.citation_count || 0) - (a.citation_count || 0))
    : router?.winners || [];
  if (!rows.length) return null;
  const reasons = Object.fromEntries((router?.abstentions || []).map((a) => [a.url, a.reason]));
  const max = Math.max(...rows.map((w) => w.citation_count || 0), 1);
  return (
    <div>
      <p className="rc-pane__title">
        {title ?? "What AI cites for this question"}
        <InfoTip id="citations_panel" />
      </p>
      <div className="rc-cites">
        {rows.map((w) => {
          const unread = w.status != null && w.status !== "ok";
          const abstained = w.source_type === "other";
          return (
            <div className={`rc-cite${abstained || unread ? " rc-cite--dim" : ""}`} key={w.url}>
              <span className="rc-cite__domain">
                <a href={w.url} target="_blank" rel="noreferrer">{urlLabel(w.url)}</a>
                {unread && (
                  <span className="rc-cite__unread" title={`could not be fetched (${w.status})`}>
                    {" "}· not fetched
                  </span>
                )}
              </span>
              <span
                className="rc-cite__type"
                title={
                  unread ? `could not be fetched: ${w.status}`
                  : abstained ? `abstained: ${reasons[w.url] ?? "no classification"}`
                  : w.page_type ?? undefined
                }
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
      {router?.qc_share != null && (
        <p className="rc-cites__qcnote">
          QC is cited in {pctLabel(router.qc_share)} of responses for this question.
          <InfoTip id="losing_question" />
        </p>
      )}
    </div>
  );
}
