import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import { CompetitorWinRate } from "./CompetitorWinRate";

const ALL_SCHOOLS = [
  "All",
  "General",
  "QC Pet Studies",
  "QC Event Planning",
  "QC Design School",
  "QC Makeup Academy",
  "QC Wellness Studies",
];

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

// ─── single competitor row with expandable citations ──────────────────────────
function CompetitorRow({ rank, name, count, maxCount, expanded, onToggle, citations, loadingCitations }) {
  const pct = Math.round((count / maxCount) * 100);
  return (
    <div
      style={{ cursor: "pointer" }}
      onClick={() => onToggle(name)}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
          <span style={{ fontSize: 14, color: expanded ? PURPLE : "#c4c4c0" }}>{expanded ? "▲" : "▼"}</span>
          <span style={{ width: 20, textAlign: "right", fontSize: 12, color: "#9b9b9b" }}>
            {rank}
          </span>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
            <span style={{ fontSize: 13, color: expanded ? PURPLE : "#111", fontWeight: rank === 1 || expanded ? 500 : 400 }}>
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
  const [selectedSchool, setSelectedSchool] = useState("All");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [expandedCompetitor, setExpandedCompetitor] = useState(null);
  const [citationsCache, setCitationsCache]         = useState({});
  const [loadingCitations, setLoadingCitations]     = useState(new Set());

  // Clear citation cache whenever the effective filter changes
  useEffect(() => {
    setExpandedCompetitor(null);
    setCitationsCache({});
    setLoadingCitations(new Set());
  }, [days, school, selectedSchool]);

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

    // Effective school: local filter takes precedence over global
    const effectiveSchool = selectedSchool !== "All" ? selectedSchool
                          : (school && school !== "All") ? school
                          : null;

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

  const filtered = selectedSchool === "All"
    ? competitorsBySchool
    : competitorsBySchool.filter(c => c.school === selectedSchool);

  const aggregated = Object.values(
    filtered.reduce((acc, c) => {
      if (!acc[c.competitor]) acc[c.competitor] = { competitor: c.competitor, count: 0 };
      acc[c.competitor].count += c.count;
      return acc;
    }, {})
  ).sort((a, b) => b.count - a.count).slice(0, 10);

  const maxCount = aggregated[0]?.count ?? 1;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

      <div className="card">
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 4 }}>
          <div>
            <p className="panel-title">Top competitors mentioned</p>
            <p className="panel-subtitle">
              {selectedSchool === "All" ? "Across all schools" : `In ${selectedSchool} questions`}
            </p>
          </div>
          <select
            style={{
              fontSize: 12, color: "#6b6b6b",
              border: "0.5px solid rgba(0,0,0,0.15)",
              borderRadius: 6, padding: "4px 8px",
              background: "#fff", cursor: "pointer", flexShrink: 0,
            }}
            value={selectedSchool}
            onChange={e => setSelectedSchool(e.target.value)}
          >
            {ALL_SCHOOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {aggregated.length === 0 ? (
          <p className="state-empty">No competitor data for this selection.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
            {aggregated.map((c, i) => (
              <CompetitorRow
                key={c.competitor}
                rank={i + 1}
                name={c.competitor}
                count={c.count}
                maxCount={maxCount}
                expanded={expandedCompetitor === c.competitor}
                onToggle={toggleCompetitor}
                citations={citationsCache[c.competitor]}
                loadingCitations={loadingCitations.has(c.competitor)}
              />
            ))}
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
