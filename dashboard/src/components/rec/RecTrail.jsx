import { bucketColor, bucketLabel, domainOf, pctLabel } from "../../lib/recview";
import InfoTip from "../InfoTip";

// The router's decision path as a numbered stepper — every step carries the
// number that drove it, so the card reads as "check us", not "trust us".
// Step content mirrors route_question(): the same checks, in the same order.

function Check({ pass, gated, children }) {
  const cls = gated ? "rc-check--gated" : pass ? "rc-check--pass" : "rc-check--fail";
  return <span className={`rc-check ${cls}`}>{children}</span>;
}

// 100%-stacked vote-share meter with the 60% dominance bar drawn on it.
function VoteMeter({ vote }) {
  const buckets = Object.entries(vote?.buckets || {}).sort((a, b) => b[1] - a[1]);
  const voters = vote?.voters || buckets.reduce((s, [, n]) => s + n, 0);
  if (!voters || buckets.length === 0) return null;
  return (
    <div>
      <div className="rc-anchor">
        <span className="rc-anchor__label" style={{ left: "60%" }}>60% bar</span>
        <div
          className="rc-meter"
          role="img"
          aria-label={`Vote: ${buckets.map(([b, n]) => `${bucketLabel(b)} ${n}`).join(", ")}`}
        >
          {buckets.map(([b, n]) => (
            <i key={b} style={{ width: `${(n / voters) * 100}%`, background: bucketColor(b) }} />
          ))}
        </div>
        <span className="rc-anchor__tick" style={{ left: "60%" }} />
      </div>
      <div className="rc-meter-legend">
        {buckets.map(([b, n]) => (
          <span key={b}>
            <i className="rc-dot" style={{ background: bucketColor(b) }} />
            {bucketLabel(b)} {n}
          </span>
        ))}
      </div>
    </div>
  );
}

function losingStep(router, extra) {
  return {
    title: extra ? "Losing question, page exists" : "Losing question detected",
    info: "losing_question",
    fact: (
      <>
        QC cited in <b>{pctLabel(router.qc_share)}</b> of <b>{router.n_citations ?? "?"}</b> citations
        {extra ? " despite a covering page" : ""}
      </>
    ),
  };
}

function voteStep(router, vote) {
  return {
    title: "Dominance vote",
    info: "dominance_vote",
    meter: vote,
    fact: (
      <>
        {bucketLabel(router.dominant_source)} <b>{pctLabel(router.dominant_share)}</b>{" "}
        {vote.cleared_bar
          ? <>≥ 60% bar · <Check pass>cleared</Check></>
          : <>· <Check gated>below 60% bar</Check></>}
      </>
    ),
  };
}

function fixSteps(rec) {
  const router = rec.detail?.router ?? {};
  const vote = router.vote ?? {};
  const sc = rec.detail?.scorecard;
  const tier = rec.detail?.evidence_tier;
  const gaps =
    rec.detail?.evidence_grade?.checklist_gaps?.length ??
    (sc?.features || []).filter((f) => f.recommend).length;

  const steps = [
    losingStep(router, true),
    // Fix only fires when the ownable side cleared the dominance bar — show
    // that check here so this trail and any companion reach-out trails on the
    // same question visibly agree about ownability.
    ...(vote.voters
      ? [
          voteStep(router, vote),
          {
            title: "Ownable check",
            info: "ownable_check",
            fact: (
              <>
                <Check pass>ownable {pctLabel(vote.ownable_share)}</Check> — QC can win this slot
                with its own page
              </>
            ),
          },
        ]
      : []),
    {
      title: "Genre check",
      info: "genre_check",
      fact: (
        <>
          Cited winners are the same kind of page as QC's — the page itself underperforms ·{" "}
          <Check pass>fixable</Check>
        </>
      ),
    },
  ];
  if (sc) {
    const unread = sc.winners_unreadable?.length ?? 0;
    steps.push({
      title: "Feature diff",
      info: "feature_diff",
      fact: (
        <>
          QC page compared against <b>{sc.winners_total}</b>
          {sc.winners_cited_total !== sc.winners_total ? <> of <b>{sc.winners_cited_total}</b></> : null}{" "}
          cited pages across <b>{sc.features?.length ?? 0}</b> GEO features
          {unread ? ` (${unread} unfetchable)` : ""}
        </>
      ),
    });
    steps.push({
      title: "Gap threshold",
      info: "gap_threshold",
      fact:
        gaps > 0 ? (
          <>
            <b>{gaps}</b> feature{gaps === 1 ? "" : "s"} most winners have, QC lacks ·{" "}
            <Check pass={tier === "high"} gated={tier !== "high"}>
              {tier === "high" ? "high evidence tier" : "low evidence tier"}
            </Check>
          </>
        ) : (
          <>
            No verified gaps — weaker signals only (sub-threshold / LLM-observed) ·{" "}
            <Check gated>low evidence tier</Check>
          </>
        ),
    });
  }
  steps.push({
    title: "Verdict: FIX",
    fact: "Right page, missing structure — patch the gaps.",
    verdict: true,
  });
  return steps;
}

function reachSteps(rec) {
  const router = rec.detail?.router ?? {};
  const vote = router.vote ?? {};
  const feas = rec.detail?.outreach_feasibility ?? router.outreach_feasibility;
  const target = rec.target;
  const winner = (router.winners || []).find((w) => w.url === target);

  // Fan-out companions ride along on a question whose field the router judged
  // OWNABLE (fix/build won the routing) — for those, "an owned page can't
  // take this slot" would contradict the primary card's own trail. Only claim
  // non-ownability when the non-ownable side actually cleared the bar.
  const slotOwnable =
    router.branch === "reach_out_fanout" && (vote.non_ownable_share ?? 0) < 0.6;

  const steps = [
    losingStep(router),
    voteStep(router, vote),
    slotOwnable
      ? {
          title: "Ownable check",
          info: "ownable_check",
          fact: (
            <>
              <Check pass>ownable {pctLabel(vote.ownable_share)}</Check> — the owned-page play can
              win this slot; this card adds QC presence on a source engines also cite
            </>
          ),
        }
      : {
          title: "Ownable check",
          info: "ownable_check",
          fact: (
            <>
              {bucketLabel(router.dominant_source)} sources win ·{" "}
              <Check pass={false}>non-ownable {pctLabel(vote.non_ownable_share)}</Check> — an owned
              page can't take this slot
            </>
          ),
        },
  ];
  if (target) {
    steps.push({
      title: "Target selection",
      info: "target_selection",
      fact: (
        <>
          Most-cited pitchable winner: <b>{domainOf(target)}</b>
          {winner ? <>, cited <b>{winner.citation_count}×</b></> : null}
        </>
      ),
    });
  }
  if (feas) {
    const gated = feas.feasibility === "gated";
    steps.push({
      title: "Channel probe",
      info: "channel",
      fact: (
        <>
          {feas.evidence || feas.mechanism} ·{" "}
          <Check pass={!gated} gated={gated}>channel: {feas.feasibility}</Check>
        </>
      ),
    });
  }
  steps.push({
    title: "Verdict: REACH OUT",
    fact: slotOwnable
      ? "Companion play — earn extra presence on the sources engines already cite."
      : "Can't own the slot — earn it on the source engines already trust.",
    verdict: true,
  });
  return steps;
}

function buildSteps(rec) {
  const router = rec.detail?.router ?? {};
  const vote = router.vote ?? {};
  const gm = router.genre_mismatch;
  const abstained = router.abstentions?.length ?? 0;

  const steps = [
    losingStep(router),
    {
      title: "Cited pages classified",
      info: "vote_voters",
      fact: (
        <>
          <b>{vote.voters ?? 0}</b> voters
          {abstained ? <> · <b>{abstained}</b> abstained (unread page, no domain rule)</> : null}
        </>
      ),
    },
    voteStep(router, vote),
    {
      title: "Ownable check",
      info: "ownable_check",
      fact: (
        <>
          <Check pass>ownable {pctLabel(vote.ownable_share)}</Check> — QC can own this slot
        </>
      ),
    },
  ];
  if (gm) {
    steps.push({
      title: "Coverage check",
      info: "coverage_check",
      fact: (
        <>
          QC's page is <b>{gm.qc_genre}</b>; <b>{gm.winners_with_genre}/{gm.winners_classified}</b>{" "}
          classifiable winners are <b>{gm.winner_genre}</b> · <Check pass={false}>genre mismatch</Check>
        </>
      ),
    });
  } else if (router.reason === "earn_indirect") {
    steps.push({
      title: "Coverage check",
      info: "coverage_check",
      fact: (
        <>
          Winners are reference sources with no direct channel — earn the citation indirectly ·{" "}
          <Check gated>indirect</Check>
        </>
      ),
    });
  } else {
    steps.push({
      title: "Coverage check",
      info: "coverage_check",
      fact: <>No QC page answers this query · <Check pass={false}>no coverage</Check></>,
    });
  }
  steps.push({
    title: "Verdict: BUILD",
    fact: "Ownable field, no matching QC page — build it.",
    verdict: true,
  });
  return steps;
}

export default function RecTrail({ rec, variant }) {
  if (!rec.detail?.router) return null;
  const steps =
    variant === "fix" ? fixSteps(rec) : variant === "reach" ? reachSteps(rec) : buildSteps(rec);
  return (
    <div className="rc-trail">
      {steps.map((s, i) => (
        <div className={`rc-step${s.verdict ? " rc-step--verdict" : ""}`} key={s.title}>
          <span className="rc-step__n">{s.verdict ? "→" : i + 1}</span>
          <div className="rc-step__body">
            <p className="rc-step__title">
              {s.title}
              {s.info && <InfoTip id={s.info} />}
            </p>
            {s.fact && <p className="rc-step__fact">{s.fact}</p>}
            {s.meter && <VoteMeter vote={s.meter} />}
          </div>
        </div>
      ))}
    </div>
  );
}
