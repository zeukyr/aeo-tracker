import { urlLabel } from "../../lib/recview";
import InfoTip from "../InfoTip";

// One pitchable destination, consolidated so a PR person can act without
// opening anything: proof it matters (citations), proof it's winnable
// (lists rivals / never QC — inclusion recs only), and the channel mechanics.
export default function TargetDossier({ rec }) {
  const router = rec.detail?.router ?? {};
  const feas = rec.detail?.outreach_feasibility ?? router.outreach_feasibility;
  const opp = rec.detail?.opportunity;
  const target = opp?.url ?? rec.target;
  if (!target) return null;

  const winner = (router.winners || []).find((w) => w.url === target);
  const cited = opp?.citation_count ?? winner?.citation_count;
  const voters = router.vote?.voters;
  const gated = feas?.feasibility === "gated";

  return (
    <div>
      <p className="rc-pane__title">
        Target dossier
        <InfoTip id="target_selection" />
      </p>
      <div className="rc-dossier">
        <div className="rc-dossier__head">
          <span className="rc-dossier__url">
            <a href={target} target="_blank" rel="noreferrer">{urlLabel(target)}</a>
          </span>
          {cited != null && <span className="rc-dossier__cited">cited {cited}× ↗</span>}
        </div>
        <div className="rc-dossier__grid">
          {cited != null && (
            <>
              <span className="rc-dossier__key">Why it matters</span>
              <p className="rc-dossier__val">
                Top-cited source for this question
                {voters ? <> — <b>{cited} of {voters}</b> voter citations point here.</> : "."}
              </p>
            </>
          )}
          {opp?.lists_competitors?.length > 0 && (
            <>
              <span className="rc-dossier__key">Who's present</span>
              <p className="rc-dossier__val">
                <span className="rc-rivals">
                  {opp.lists_competitors.map((r) => (
                    <span className="rc-rival" key={r}>{r}</span>
                  ))}
                </span>
              </p>
            </>
          )}
          {opp && (
            <>
              <span className="rc-dossier__key">QC status</span>
              <p className="rc-dossier__val">
                <span className="rc-neverqc">✗ Never mentions QC</span> — verified from fetched page content.
              </p>
            </>
          )}
          {feas && (
            <>
              <span className="rc-dossier__key">Channel</span>
              <p className="rc-dossier__val">
                <span className={`chip ${gated ? "chip--gated" : "chip--open"}`}>{feas.feasibility}</span>{" "}
                {gated ? "application/approval required — budget lead time" : "self-serve, no approval needed"}
              </p>
            </>
          )}
        </div>
        {feas?.mechanism && (
          <p className="rc-mechanism"><b>The play:</b> {feas.mechanism}</p>
        )}
      </div>
    </div>
  );
}
