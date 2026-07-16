// Why the router declined to produce a rec for a question, in card-ready
// prose. Falls back to the raw reason slug for reasons added later. Shared
// by QuestionDetail.jsx and the Recommendations tab's question picker, since
// both drive the same on-demand per-question generation endpoint.
export const REC_TRIAGE_MESSAGES = {
  no_mention_responses: "This question has no mention responses yet — nothing to route.",
  no_cited_winners: "QC loses this question but the responses cite no external pages to analyze.",
  insufficient_voters: "Too few classifiable citations to call a verdict.",
  fragmented_field: "No single source type dominates the cited winners — needs a human call.",
  feasibility_unknown: "The winning sources can't be owned and no outreach channel was found.",
  reputation_no_channel: "Reputation question with nothing to pitch.",
  // Legacy slug — only reachable when the scorecard itself threw; the three
  // precise reasons below replaced it for normal empty results.
  fix_no_feature_gaps: "The scorecard comparison could not produce a recommendation for QC's page.",
  fix_qc_page_unreadable: "QC's own page could not be fetched or read, so no feature comparison is possible — fix crawlability/access first (AI engines may not be able to read it either).",
  fix_true_feature_parity: "QC's page genuinely matches the analyzed cited winners on every scorecard feature, and no weaker signal surfaced — the gap isn't on-page structure.",
};

// fix_insufficient_winner_data carries counts + the unreadable URLs, so the
// message can disclose exactly what was and wasn't analyzed instead of
// asserting parity over a sample it never had.
export function recTriageMessage(triage) {
  const reason = triage?.reason;
  if (reason === "fix_insufficient_winner_data") {
    const sc = triage.scorecard || {};
    const unreadable = sc.winners_unreadable || [];
    const failedList = unreadable.map((w) => w.url).join(", ");
    return `Only ${sc.winners_readable ?? 0} of ${sc.winners_cited_total ?? "?"} cited pages could be analyzed`
      + (unreadable.length ? ` (${unreadable.length} could not be fetched: ${failedList})` : "")
      + " — not enough data to compare QC's page against the winners.";
  }
  return REC_TRIAGE_MESSAGES[reason] ?? `The router couldn't action this question (${reason ?? "unknown"}).`;
}
