import { useEffect, useState } from "react";
import { API_BASE_URL } from "../../config";
import { useFilter } from "../../context/useFilter";
import InfoTip from "../InfoTip";
import { urlLabel } from "../../lib/recview";
import { downloadRedditSpotlightXlsx } from "../../lib/redditSpotlightExport";

// Reddit is one domain but two different plays: threads that already name QC
// (correct the record) versus threads that never mention QC (earn the
// citation by answering authentically). Comprehensive/unfiltered - every
// reddit.com URL ever cited, no threshold or lifecycle - so it's the Reddit
// half of Outreach & Earn's split (Reddit / get mentioned in third parties);
// reddit-targeted reach-out/inclusion recs are filtered out of the other
// half's card list (Recommendations.jsx's isRedditTarget) so Reddit only
// ever appears here, not duplicated as a weaker rec card too.

function SubredditChips({ subreddits }) {
  if (!subreddits.length) return null;
  return (
    <div className="reddit-subs">
      {subreddits.map((s) => (
        <span className="reddit-sub" key={s.subreddit}>
          r/{s.subreddit} <b>{s.total_count}</b>
        </span>
      ))}
    </div>
  );
}

// Reddit blocks this server's own lookups (403, even with a browser UA), so
// there's no automated way to tell whether a thread is archived or against
// a subreddit's rules - a human confirms it during outreach and marks it
// here. PUTs straight to reddit_thread_status (migration 007) and feeds back
// into ranking on the next fetch.
function markThreadStatus(t, status, reason) {
  return fetch(`${API_BASE_URL}/api/recommendations/reddit-targets/${t.post_id}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: t.url, subreddit: t.subreddit, status, reason }),
  });
}

function ThreadStatusControl({ t, onMarked }) {
  const [busy, setBusy] = useState(false);
  if (!t.post_id) return null;

  const mark = async (status, reason) => {
    setBusy(true);
    try {
      await markThreadStatus(t, status, reason);
      onMarked(t.post_id, status, reason);
    } finally {
      setBusy(false);
    }
  };

  if (t.dead) {
    return (
      <button type="button" className="btn btn--ghost reddit-thread__mark" disabled={busy} onClick={() => mark("open", null)}>
        Undo
      </button>
    );
  }
  return (
    <span className="reddit-thread__mark-group">
      <button type="button" className="btn btn--ghost reddit-thread__mark" disabled={busy} onClick={() => mark("dead", "archived")}>
        Mark archived
      </button>
      <button type="button" className="btn btn--ghost reddit-thread__mark" disabled={busy} onClick={() => mark("dead", "against subreddit rules")}>
        Mark against rules
      </button>
    </span>
  );
}

function ThreadRow({ t, onMarked }) {
  return (
    <div className={`reddit-thread${t.dead || t.restricted ? " reddit-thread--blocked" : ""}`}>
      <div className="reddit-thread__head">
        <span className="reddit-thread__sub">r/{t.subreddit ?? "reddit"}</span>
        {t.dead && (
          <span className="chip chip--dead" title={`Manually marked ${t.dead_reason || "unavailable"} — can't be replied to.`}>
            {t.dead_reason === "archived" ? "Archived — can't comment" : "Against subreddit rules"}
          </span>
        )}
        <a className="reddit-thread__url" href={t.url} target="_blank" rel="noreferrer">
          {urlLabel(t.url)}
        </a>
        <span className="reddit-thread__count">{t.total_count}×</span>
        <ThreadStatusControl t={t} onMarked={onMarked} />
      </div>
      {t.questions.length > 0 && (
        <ul className="reddit-thread__questions">
          {t.questions.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ParticipationStrategy({ steps }) {
  if (!steps || !steps.length) return null;
  return (
    <details className="reddit-strategy">
      <summary>How to participate</summary>
      <ol>
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </details>
  );
}

function ThreadGroup({ title, note, accent, items, strategy, onMarked }) {
  if (!items.length) return null;
  return (
    <div className="reddit-group">
      <p className={`reddit-group__title reddit-group__title--${accent}`}>{title}</p>
      <p className="reddit-group__note">{note}</p>
      <ParticipationStrategy steps={strategy} />
      <div className="reddit-threads">
        {items.map((t) => (
          <ThreadRow t={t} key={t.url} onMarked={onMarked} />
        ))}
      </div>
    </div>
  );
}

export default function RedditSpotlight() {
  const { days, school } = useFilter();
  const [data, setData] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);
    if (school && school !== "All") params.append("school", school);

    fetch(`${API_BASE_URL}/api/recommendations/reddit-targets?${params}`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ threads: [], subreddits: [], strategy: {} }));
  }, [days, school]);

  if (!data || data.threads.length === 0) return null;

  // Marking a thread updates in place rather than re-fetching/re-sorting -
  // the badge and the "reopen" control need to reflect the change
  // immediately, but reshuffling the list out from under someone mid-review
  // would be jarring. The new rank takes effect next time the panel loads.
  const handleMarked = (postId, status, reason) => {
    setData((prev) => ({
      ...prev,
      threads: prev.threads.map((t) =>
        t.post_id === postId
          ? { ...t, dead: status === "dead", dead_reason: status === "dead" ? reason : null, actionable: !t.restricted && status !== "dead" }
          : t
      ),
    }));
  };

  const reply = data.threads.filter((t) => t.category === "reputation");
  const discover = data.threads.filter((t) => t.category === "discovery");
  const strategy = data.strategy || {};

  return (
    <div className="card reddit-spotlight">
      <div className="reddit-spotlight__head">
        <p className="panel-title">
          Reddit spotlight
          <InfoTip id="reddit_spotlight" />
        </p>
        <button
          type="button"
          className="btn btn--ghost reddit-spotlight__export"
          onClick={() => downloadRedditSpotlightXlsx(data.threads, strategy)}
        >
          Download spreadsheet
        </button>
      </div>
      <p className="panel-subtitle">
        Where AI actually goes on Reddit for QC's topics — split by whether QC is already part of the conversation.
      </p>

      <SubredditChips subreddits={data.subreddits} />

      <ThreadGroup
        title={`Reply & correct the record · ${reply.length}`}
        note="QC's name is already in these threads — reply or host an AMA, don't pitch."
        accent="reply"
        items={reply}
        strategy={strategy.reputation}
        onMarked={handleMarked}
      />
      <ThreadGroup
        title={`Answer & get discovered · ${discover.length}`}
        note="QC isn't part of these conversations yet — an authentic answer here can earn the citation."
        accent="discover"
        items={discover}
        strategy={strategy.discovery}
        onMarked={handleMarked}
      />
    </div>
  );
}
