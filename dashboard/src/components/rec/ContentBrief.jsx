import InfoTip from "../InfoTip";

// Same three sections regardless of which engine produced the rec (concern,
// credibility-adjacent reframe, or competitive-content) - Page heading /
// Suggested structure / Format requirements - so a writer scans one layout
// instead of re-parsing a different wall of text each time. The strategy
// sentence itself already renders as the card's action summary above this
// module, so it isn't repeated here - this module only adds what that
// summary doesn't cover. `outline` renders as an explicit empty state rather
// than disappearing when a concern type has no authored structure yet, so
// "checked, nothing here" stays distinguishable from "never built".
const FORMAT_CHECKLIST = (heading) => [
  <><b>H2</b> — exact phrase "{heading}"</>,
  <><b>First sentence</b> — direct answer, no lead-up</>,
  <><b>Schema</b> — FAQPage markup</>,
  <><b>Tone</b> — no marketing adjectives</>,
];

export default function ContentBrief({ brief }) {
  if (!brief) return null;
  const { heading, outline, evidence_quotes: quotes } = brief;

  return (
    <div>
      <p className="rc-pane__title">
        Content brief
        <InfoTip id="content_brief" />
      </p>

      <div className="rc-brief">
        {heading && (
          <div className="rc-brief__section">
            <span className="rc-brief__eyebrow">Page heading</span>
            <div className="rc-brief__heading">
              <span className="rc-brief__heading-tag">H2</span>
              <span className="rc-brief__heading-text">"{heading}"</span>
            </div>
          </div>
        )}

        {quotes?.length > 0 && (
          <div className="rc-brief__section">
            <span className="rc-brief__eyebrow">What engines actually say</span>
            <div className="rc-brief__quotes">
              {quotes.map((q, i) => (
                <p className="rc-brief__quote" key={i}>"{q}"</p>
              ))}
            </div>
          </div>
        )}

        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Suggested structure</span>
          {outline?.length ? (
            <div className="rc-trail">
              {outline.map((o, i) => (
                <div className="rc-step" key={o.title}>
                  <span className="rc-step__n">{i + 1}</span>
                  <div className="rc-step__body">
                    <p className="rc-step__title">{o.title}</p>
                    <p className="rc-step__fact">{o.detail}</p>
                    {o.confirm_with_qc && (
                      <span className="rc-brief__confirm">⚠ confirm with QC before publishing</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="rc-brief__empty">
              No outline authored for this type yet — start from the format requirements below.
            </p>
          )}
        </div>

        {heading && (
          <div className="rc-brief__section">
            <span className="rc-brief__eyebrow">Format requirements</span>
            <div className="rc-brief__checklist">
              {FORMAT_CHECKLIST(heading).map((item, i) => (
                <div className="rc-brief__check" key={i}>
                  <span className="rc-brief__check-mark">✓</span> {item}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
