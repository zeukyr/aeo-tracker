import InfoTip from "../InfoTip";
import { formatColor, formatLabel } from "../../lib/recview";

// Pure presentation of a deterministic, format-templated build_page_plan()
// payload (api/queries/scorecard.py) - never reimplements the section
// skeleton or targets in JS, so there's exactly one place ("what does a
// how-to/blog/listicle/landing page need") that can drift.
const UNIT_SUFFIX = { pct: "%", levels: " levels" };

export default function PagePlan({ plan }) {
  if (!plan) return null;
  const { format, format_label: formatLabelText, sections, word_count_target: wc, structure_targets: targets } = plan;

  return (
    <div>
      <p className="rc-pane__title">
        Page plan
        <InfoTip id="page_plan" />
      </p>

      <div className="rc-brief">
        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Format</span>
          <div className="rc-plan__format">
            <i className="rc-dot" style={{ background: formatColor(format) }} />
            {formatLabelText ?? formatLabel(format)}
            {wc && (
              <span className="rc-plan__wordcount">
                · ~{wc.value.toLocaleString()} words (median of {wc.based_on_n_winners} cited pages)
              </span>
            )}
          </div>
        </div>

        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Suggested structure</span>
          <div className="rc-trail">
            {sections.map((s, i) => (
              <div className="rc-step" key={s.title}>
                <span className="rc-step__n">{i + 1}</span>
                <div className="rc-step__body">
                  <p className="rc-step__title">{s.title}</p>
                  <p className={`rc-step__fact${s.source === "template" && !s.example ? " rc-step__fact--template" : ""}`}>
                    {s.detail}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {targets?.length > 0 && (
          <div className="rc-brief__section">
            <span className="rc-brief__eyebrow">Structure targets</span>
            <div className="rc-brief__checklist">
              {targets.map((t) => (
                <div className="rc-brief__check" key={t.id}>
                  <b>{t.label}</b>: aim for {t.target_min}–{t.target_max}{UNIT_SUFFIX[t.unit] ?? ""}
                  {t.guidance && <> — {t.guidance}</>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
