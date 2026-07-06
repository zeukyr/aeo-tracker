import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import { CompetitorWinRate } from "./CompetitorWinRate";

const PURPLE = "#2563eb";
const QC_RE  = /qccareerschool|qcpetstudies|qceventplanning|qcdesignschool|qcmakeupacademy/i;

// ─── citation panel shown when a competitor is expanded ───────────────────────
function CitationsPanel({ citations, loading }) {
  if (loading) {
    return <p style={{ fontSize: 12, color: "#9b9b9b", fontStyle: "italic", padding: "8px 0 4px" }}>Loading…</p>;
  }
  if (!citations) return null;
  if (!citations.length) {
    return <p style={{ fontSize: 12, color: "#9b9b9b", padding: "8px 0 4px" }}>No citations found for this competitor.</p>;
  }

  const maxCount = citations[0].count;
  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid #f0efec" }}>
      <p style={{ fontSize: 10, fontWeight: 700, color: "#9b9b9b", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
        Most cited pages
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {citations.map((c, i) => {
          const isQC  = QC_RE.test(c.url ?? "");
          const pct   = Math.round((c.count / maxCount) * 100);
          const color = isQC ? "#378add" : PURPLE;

          let display = c.url ?? "";
          try { display = new URL(c.url).hostname.replace(/^www\./, "") + new URL(c.url).pathname; }
          catch {}

          return (
            <div key={c.url ?? i}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={e => e.stopPropagation()}
                  title={c.url}
                  style={{
                    fontSize: 12, color,
                    textDecoration: "none",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    maxWidth: "85%",
                  }}
                >
                  {display}
                </a>
                <span style={{ fontSize: 11, color: "#6b6b6b", flexShrink: 0, marginLeft: 8 }}>{c.count}</span>
              </div>
              <div style={{ height: 3, background: "#f0efec", borderRadius: 99, overflow: "hidden" }}>
                <div style={{
                  height: "100%", width: `${pct}%`,
                  background: color, opacity: 0.35 + 0.65 * (c.count / maxCount),
                  borderRadius: 99, transition: "width 0.4s ease",
                }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// fixed widths for the right-side metric columns only
const COL = { left: 44, avgRank: 72, sov: 52 };

function ColHeader({ label, colKey, sortBy, onSort, width, style = {} }) {
  const active = sortBy === colKey;
  return (
    <button
      onClick={() => onSort(colKey)}
      style={{
        width, flexShrink: 0,
        textAlign: "right", fontSize: 10, fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.06em",
        color: active ? PURPLE : "#9b9b9b",
        background: "none", border: "none", cursor: "pointer",
        padding: 0, display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 3,
        ...style,
      }}
    >
      {label}
      <span style={{ fontSize: 9 }}>{active ? "▼" : ""}</span>
    </button>
  );
}

// ─── single competitor row with expandable citations ──────────────────────────
function CompetitorRow({ rank, name, count, maxCount, shareOfVoice, avgRank, expanded, onToggle, citations, loadingCitations }) {
  const pct = Math.round((count / maxCount) * 100);
  return (
    <div style={{ cursor: "pointer" }} onClick={() => onToggle(name)}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {/* arrow + rank */}
        <div style={{ width: COL.left, display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
          <span style={{ fontSize: 14, color: expanded ? PURPLE : "#c4c4c0" }}>{expanded ? "▲" : "▼"}</span>
          <span style={{ width: 20, textAlign: "right", fontSize: 12, color: "#9b9b9b" }}>{rank}</span>
        </div>
        {/* name + count integrated with bar */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
            <span style={{
              fontSize: 13, color: expanded ? PURPLE : "#111",
              fontWeight: rank === 1 || expanded ? 500 : 400,
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              marginRight: 8,
            }}>
              {name}
            </span>
            <span style={{ fontSize: 12, color: "#6b6b6b", flexShrink: 0 }}>{count}</span>
          </div>
          <div style={{ height: 5, background: "#f0efec", borderRadius: 99, overflow: "hidden" }}>
            <div style={{
              height: "100%", width: `${pct}%`,
              background: PURPLE, opacity: 0.4 + 0.6 * (count / maxCount),
              borderRadius: 99, transition: "width 0.4s ease",
            }} />
          </div>
        </div>
        {/* right-side metric columns */}
        <span style={{ width: COL.avgRank, textAlign: "right", fontSize: 12, color: "#6b6b6b", flexShrink: 0 }}>#{avgRank}</span>
        <span style={{ width: COL.sov,     textAlign: "right", fontSize: 12, color: "#6b6b6b", flexShrink: 0 }}>{shareOfVoice}%</span>
      </div>

      {expanded && (
        <div style={{ paddingLeft: 50 }}>
          <CitationsPanel citations={citations} loading={loadingCitations} />
        </div>
      )}
    </div>
  );
}

// ─── main Competitors component ───────────────────────────────────────────────
function Competitors() {
  const { days, school } = useFilter();
  const [competitorsBySchool, setCompetitorsBySchool] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [expandedCompetitor, setExpandedCompetitor] = useState(null);
  const [citationsCache, setCitationsCache]         = useState({});
  const [loadingCitations, setLoadingCitations]     = useState(new Set());
  const [sortBy, setSortBy]                         = useState("count");

  // Clear citation cache whenever the effective filter changes
  useEffect(() => {
    setExpandedCompetitor(null);
    setCitationsCache({});
    setLoadingCitations(new Set());
  }, [days, school]);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (days) params.append("days", days);
    if (school && school !== "All") params.append("school", school);

    fetch(`${API_BASE_URL}/api/top-competitors-by-school?${params}`)
      .then(r => r.json())
      .then(data => { setCompetitorsBySchool(data); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [days, school]);

  function toggleCompetitor(name) {
    if (expandedCompetitor === name) {
      setExpandedCompetitor(null);
      return;
    }
    setExpandedCompetitor(name);

    if (citationsCache[name] !== undefined || loadingCitations.has(name)) return;

    const effectiveSchool = (school && school !== "All") ? school : null;

    setLoadingCitations(prev => new Set([...prev, name]));
    const params = new URLSearchParams({ competitor: name });
    if (days) params.append("days", days);
    if (effectiveSchool) params.append("school", effectiveSchool);

    fetch(`${API_BASE_URL}/api/competitor-citations?${params}`)
      .then(r => r.json())
      .then(data => {
        setCitationsCache(prev => ({ ...prev, [name]: data }));
        setLoadingCitations(prev => { const next = new Set(prev); next.delete(name); return next; });
      })
      .catch(() => {
        setCitationsCache(prev => ({ ...prev, [name]: [] }));
        setLoadingCitations(prev => { const next = new Set(prev); next.delete(name); return next; });
      });
  }

  if (loading) return <p className="state-msg">Loading...</p>;
  if (error)   return <p className="state-msg state-msg--error">Error: {error}</p>;

  const base = Object.values(
    competitorsBySchool.reduce((acc, c) => {
      if (!acc[c.competitor]) acc[c.competitor] = { competitor: c.competitor, count: 0, sum_rank: 0 };
      acc[c.competitor].count += c.count;
      acc[c.competitor].sum_rank += c.sum_rank ?? 0;
      return acc;
    }, {})
  ).slice(0, 10);

  const totalCount = base.reduce((s, c) => s + c.count, 0);

  // Attach derived metrics then sort
  const withMetrics = base.map(c => ({
    ...c,
    shareOfVoice: Math.round(c.count / totalCount * 100),
    avgRank: parseFloat((c.sum_rank / c.count).toFixed(1)),
  }));

  const aggregated = [...withMetrics].sort((a, b) => {
    if (sortBy === "avgRank") return a.avgRank - b.avgRank;   // lower = better
    if (sortBy === "sov")     return b.shareOfVoice - a.shareOfVoice;
    return b.count - a.count;
  });

  const maxCount = Math.max(...aggregated.map(c => c.count), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

      <div className="card">
        <div style={{ marginBottom: 4 }}>
          <p className="panel-title">Top competitors mentioned</p>
          <p className="panel-subtitle">Across all schools</p>
        </div>

        {aggregated.length === 0 ? (
          <p className="state-empty">No competitor data for this selection.</p>
        ) : (
          <div style={{ marginTop: 8 }}>
            {/* table header */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, paddingBottom: 6, borderBottom: "1px solid #f0efec", marginBottom: 6 }}>
              <div style={{ width: COL.left, flexShrink: 0 }} />
              <div style={{ flex: 1, display: "flex", justifyContent: "flex-end" }}>
                <ColHeader label="Citations" colKey="count" sortBy={sortBy} onSort={setSortBy} width="auto" />
              </div>
              <ColHeader label="Avg rank" colKey="avgRank" sortBy={sortBy} onSort={setSortBy} width={COL.avgRank} />
              <ColHeader label="SoV"      colKey="sov"     sortBy={sortBy} onSort={setSortBy} width={COL.sov} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {aggregated.map((c, i) => (
                <CompetitorRow
                  key={c.competitor}
                  rank={i + 1}
                  name={c.competitor}
                  count={c.count}
                  maxCount={maxCount}
                  shareOfVoice={c.shareOfVoice}
                  avgRank={c.avgRank}
                  expanded={expandedCompetitor === c.competitor}
                  onToggle={toggleCompetitor}
                  citations={citationsCache[c.competitor]}
                  loadingCitations={loadingCitations.has(c.competitor)}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <p className="panel-title">Competitor win rate</p>
        <p className="panel-subtitle">How often each competitor is recommended over QC in direct comparison questions</p>
        <CompetitorWinRate />
      </div>

    </div>
  );
}

export default Competitors;
