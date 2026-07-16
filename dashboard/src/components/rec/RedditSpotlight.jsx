import { useEffect, useState } from "react";
import { API_BASE_URL } from "../../config";
import { useFilter } from "../../context/useFilter";
import InfoTip from "../InfoTip";
import { urlLabel } from "../../lib/recview";

// Reddit is one domain but two different plays: threads that already name QC
// (correct the record) versus threads that never mention QC (earn the
// citation by answering authentically). Lives in the Outreach & Earn tab
// because both plays are community work, not page work.

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

function ThreadRow({ t }) {
  return (
    <div className="reddit-thread">
      <div className="reddit-thread__head">
        <span className="reddit-thread__sub">r/{t.subreddit ?? "reddit"}</span>
        {t.is_qc_subreddit && (
          <span className="chip chip--metric" title="A QC-branded subreddit — confirm who runs it before pitching.">
            QC-branded
          </span>
        )}
        <a className="reddit-thread__url" href={t.url} target="_blank" rel="noreferrer">
          {urlLabel(t.url)}
        </a>
        <span className="reddit-thread__count">{t.total_count}×</span>
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

function ThreadGroup({ title, note, accent, items }) {
  if (!items.length) return null;
  return (
    <div className="reddit-group">
      <p className={`reddit-group__title reddit-group__title--${accent}`}>{title}</p>
      <p className="reddit-group__note">{note}</p>
      <div className="reddit-threads">
        {items.map((t) => (
          <ThreadRow t={t} key={t.url} />
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
      .catch(() => setData({ threads: [], subreddits: [] }));
  }, [days, school]);

  if (!data || data.threads.length === 0) return null;

  const reply = data.threads.filter((t) => t.category === "reputation");
  const discover = data.threads.filter((t) => t.category === "discovery");

  return (
    <div className="card reddit-spotlight">
      <p className="panel-title">
        Reddit spotlight
        <InfoTip id="reddit_spotlight" />
      </p>
      <p className="panel-subtitle">
        Where AI actually goes on Reddit for QC's topics — split by whether QC is already part of the conversation.
      </p>

      <SubredditChips subreddits={data.subreddits} />

      <ThreadGroup
        title={`Reply & correct the record · ${reply.length}`}
        note="QC's name is already in these threads — reply or host an AMA, don't pitch."
        accent="reply"
        items={reply}
      />
      <ThreadGroup
        title={`Answer & get discovered · ${discover.length}`}
        note="QC isn't part of these conversations yet — an authentic answer here can earn the citation."
        accent="discover"
        items={discover}
      />
    </div>
  );
}
