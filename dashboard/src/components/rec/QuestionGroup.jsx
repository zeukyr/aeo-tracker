import RecommendationCard from "../RecommendationCard";
import RecRow from "./RecRow";
import { pctLabel } from "../../lib/recview";

// One question with 2+ pitchable channels (reach-out / inclusion recs sharing
// the same detail.router.question_id). Each channel collapses to a RecRow by
// default; expandedIds controls which ones show their full RecommendationCard
// instead, so a single question's shape (how many levers, how they're each
// prioritized) reads at a glance without losing per-channel detail on demand.
export default function QuestionGroup({ group, expandedIds, onToggleExpand, popoverId, cardProps }) {
  const router = group[0].detail?.router;
  return (
    <div className="rec-qgroup">
      <div className="rec-qgroup__head">
        <span className="rec-qgroup__question">{router?.question}</span>
        <span className="rec-qgroup__stats">
          {router?.n_citations != null && <>{router.n_citations} citations</>}
          {router?.qc_share != null && <> · QC cited {pctLabel(router.qc_share)}</>}
        </span>
      </div>
      <div className="rec-qgroup__rows">
        {group.map((rec) =>
          expandedIds.has(rec.id) ? (
            <RecommendationCard
              key={rec.id}
              rec={rec}
              isPopoverOpen={popoverId === rec.id}
              {...cardProps}
            />
          ) : (
            <RecRow key={rec.id} rec={rec} onToggleExpand={onToggleExpand} />
          )
        )}
      </div>
    </div>
  );
}
