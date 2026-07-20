// Copy registry for the metric info tips on recommendation cards.
// One entry per metric: 1-2 sentences on how it's calculated, plain language,
// no abbreviations. The numbers mirror backend constants — if a threshold
// changes (question_router.py, scorecard.py, prioritization.py,
// recommendation_measurement.py), update the matching entry.

export const METRIC_INFO = {
  losing_question: {
    label: "Losing question",
    text: "The share of AI responses to this question that cite a QC page, over the selected period. A question counts as losing when QC is cited in 15% or fewer of its responses.",
  },
  dominance_vote: {
    label: "Dominance vote",
    text: "Each cited page is classified by source type and votes with a weight equal to how often it was cited. A source type wins only when it holds at least 60% of the votes, and a verdict requires at least 4 voting citations.",
  },
  ownable_check: {
    label: "Ownable check",
    text: "Source types are grouped into ownable (rival providers, editorial articles — slots QC could win with its own page) versus non-ownable (forums, review platforms, reference sites, certifying bodies). The winning side decides whether the play is an owned page or outreach.",
  },
  vote_voters: {
    label: "Voters & abstentions",
    text: "Voters are cited pages that could be classified by source type, weighted by how often each was cited. Pages that could not be read and match no known domain abstain — they count neither for nor against.",
  },
  genre_check: {
    label: "Genre check",
    text: "Each page is labeled informational (a guide or how-to) or commercial (a course or program page) from its address, markup, and headings. The check passes when QC's page is the same kind as most of the winning pages.",
  },
  coverage_check: {
    label: "Coverage check",
    text: "Checks whether QC has a page answering this query, and if so, whether it is the same kind of page (informational versus commercial) as most of the cited winners.",
  },
  feature_diff: {
    label: "Feature diff",
    text: "QC's page and the top cited pages are downloaded and scored against the same checklist of features that help pages get cited by AI engines — some read directly from the page's code, others judged by an AI pass over the page text.",
  },
  gap_threshold: {
    label: "Gap threshold",
    text: "A gap is verified when at least 60% of the analyzed cited pages have a feature that QC's page lacks. Evidence is high with at least 3 readable cited pages and at least one verified gap; anything weaker is low.",
  },
  evidence_tier: {
    label: "Evidence tier",
    text: "High (“verified gap”) means at least 3 cited pages were analyzed and at least 60% of them share a feature QC's page lacks — checked against real page content. Low (“weak signal”) means only weaker hints: a thin sample, features below the 60% bar, or an AI-observed pattern.",
  },
  target_selection: {
    label: "Target selection",
    text: "The most-cited page for this question whose site can realistically be pitched (a real outreach channel exists). For “Get listed” cards, the page was also read to confirm rivals are listed and QC is not.",
  },
  channel: {
    label: "Channel",
    text: "Open means self-serve (comment, claim a profile, submit a listing); gated means someone must approve it (an editorial pitch, a listing application, an accreditation). Determined from a channel registry, the page itself, and the source type.",
  },
  priority: {
    label: "Priority & rank",
    text: "A rank within this batch: how many citations are at stake, times how badly QC is losing, boosted 1.25× when competitors repeatedly win the topic. The top quarter is high priority, the bottom quarter low.",
  },
  effort: {
    label: "Effort",
    text: "A planning hint set by the recommendation type, not computed from data: Small = a minor on-page tweak, Medium = page-level content work, Large = a new page or a sustained outreach campaign.",
  },
  confidence: {
    label: "Confidence",
    text: "A fixed score reflecting how much of the card's claim was machine-verified rather than inferred — from 80% when checked against fetched page content, down to 45% and below for weaker leads. It is not a probability of success.",
  },
  metric_target: {
    label: "Target metric",
    text: "The tracked metric this recommendation is expected to move (mention rate, citation rate, or positive sentiment) and in which direction. It becomes the success criterion once the recommendation is marked implemented.",
  },
  measurement: {
    label: "Lift measurement",
    text: "The target metric in this recommendation's segment is compared over the 30 days before versus the 30 days after implementation; the difference is the lift. A change under 5 points, or with fewer than 5 responses on either side, counts as inconclusive.",
  },
  citations_panel: {
    label: "What AI cites",
    text: "Each row is a page AI engines cited when answering this question; the count is how many times it appeared across all tracked responses in the period. Dimmed rows could not be classified and do not vote.",
  },
  feature_diff_table: {
    label: "Feature diff columns",
    text: "The weight column is the feature's importance for getting cited by AI engines; “Cited pages” is how many analyzed winners have it; “+ Add” means at least 60% of winners have it and QC doesn't; “below bar” means some winners have it, but fewer than 60%. Only verified gaps (“+ Add”) show by default — below-bar and parity rows are collapsed behind the toggle, never discarded.",
  },
  metric_rows_table: {
    label: "Structural metrics",
    text: "Measured directly from QC's page HTML (linking density, heading depth, how much content sits in lists/tables, paragraph length, bold/italic emphasis) and checked against fixed target ranges from published GEO citation-structure research — not against what the specific cited winners measure. Only out-of-range metrics show by default; in-range ones are collapsed behind the toggle, never discarded. When several are out of range, the recommendation text leads with just the one most backed by research.",
  },
  inclusion_gate: {
    label: "Inclusion opportunity",
    text: "The page was downloaded and read: rival names were found in its text, and QC's absence was verified in the same text. That direct check is why these cards carry the highest confidence.",
  },
  grouped_questions: {
    label: "Converging questions",
    text: "Near-duplicate losing questions whose citations point at the same winning pages are folded into one recommendation instead of one card each.",
  },
  health_summary: {
    label: "Health summary",
    text: "Built directly from the dashboard's own numbers: each headline metric's change versus the previous equal-length period, the questions where QC is cited in 15% or fewer responses, and the weakest engine, school, and category (minimum 5 responses to count). No AI involved, so it always matches the metric tiles.",
  },
  competitive_pattern: {
    label: "Recurring competitive pattern",
    text: "Free-text “win reasons” from head-to-head AI judgments are normalized into a fixed set of types (e.g. curriculum depth, flexibility) and rolled up across every tracked question. A pattern only fires here once it recurs on at least 2 distinct questions.",
  },
  pattern_coverage_check: {
    label: "Content probe",
    text: "QC's indexed content (sitemap pages plus every URL AI engines have ever cited) is searched for pages covering this angle; a candidate only counts as coverage when an AI pass confirms it and quotes the exact sentence.",
  },
  content_brief: {
    label: "Content brief",
    text: "The action text restructured into sections: the strategy, a page heading phrased as the actual question engines are asked, a suggested outline when one has been authored for this type, and the citability format every content rec shares. Facts the taxonomy doesn't already verify are flagged to confirm with QC, never invented.",
  },
  reddit_spotlight: {
    label: "Reddit spotlight",
    text: "Every reddit.com thread cited across tracked responses in the period, split by which kind of question surfaced it. \"Reply\" threads were cited answering a credibility question — QC's name is already in the conversation, so the play is to correct the record. \"Discovery\" threads were cited only for course/career questions — QC isn't part of the conversation yet, so the play is to answer authentically and earn the citation. Threads are ranked recency-first within each group. Use \"Mark archived\" / \"Mark against rules\" on a thread once you've checked it and can't actually comment — that's saved and reflected here from then on. Subreddits with a known blanket self-promo ban are flagged automatically. Nothing is hidden, just sorted so the actionable ones rise to the top.",
  },
};
