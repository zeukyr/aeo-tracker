import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";

const ALL_SCHOOLS = [
  "All",
  "QC Pet Studies",
  "QC Event Planning",
  "QC Design School",
  "QC Makeup Academy",
  "QC Wellness Studies",
];

function SchoolFilter({ value, onChange }) {
  return (
    <select
      style={{
        fontSize: 12,
        color: "#6b6b6b",
        border: "0.5px solid rgba(0,0,0,0.15)",
        borderRadius: 6,
        padding: "4px 8px",
        background: "#fff",
        cursor: "pointer",
        flexShrink: 0,
      }}
      value={value}
      onChange={e => onChange(e.target.value)}
    >
      {ALL_SCHOOLS.map(s => <option key={s} value={s}>{s}</option>)}
    </select>
  );
}

function CitationRow({ rank, url, count, maxCount, color }) {
  const pct = Math.round((count / maxCount) * 100);
  const domain = (() => { try { return new URL(url).hostname.replace("www.", ""); } catch { return url; } })();
  const path   = (() => { try { return new URL(url).pathname; } catch { return ""; } })();

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <span style={{ width: 20, textAlign: "right", fontSize: 12, color: "#9b9b9b", flexShrink: 0 }}>
        {rank}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
          <div style={{ minWidth: 0, marginRight: 12 }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: "#111" }}>{domain}</span>
            {path && path !== "/" && (
              <span style={{ fontSize: 11, color: "#9b9b9b", marginLeft: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {path}
              </span>
            )}
          </div>
          <span style={{ fontSize: 12, color: "#6b6b6b", flexShrink: 0 }}>{count}</span>
        </div>
        <div style={{ height: 4, background: "#f0efec", borderRadius: 99, overflow: "hidden" }}>
          <div style={{
            height: "100%",
            width: `${pct}%`,
            background: color,
            opacity: 0.4 + 0.6 * (count / maxCount),
            borderRadius: 99,
            transition: "width 0.4s ease",
          }} />
        </div>
      </div>
    </div>
  );
}

const PAGE_SIZE = 5;

function CitationList({ data, color, emptyMsg }) {
  const [visible, setVisible] = useState(PAGE_SIZE);

  useEffect(() => { setVisible(PAGE_SIZE); }, [data]);

  if (!data.length) return <p className="state-empty">{emptyMsg ?? "No data for this selection."}</p>;

  const maxCount = data[0]?.count ?? 1;
  const shown    = data.slice(0, visible);
  const hasMore  = visible < data.length;

  return (
    <div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {shown.map((c, i) => (
          <CitationRow key={c.url} rank={i + 1} url={c.url} count={c.count} maxCount={maxCount} color={color} />
        ))}
      </div>
      {hasMore && (
        <button
          onClick={() => setVisible(v => v + PAGE_SIZE)}
          style={{
            marginTop: 12,
            fontSize: 12,
            color: "#6b6b6b",
            background: "#f7f7f5",
            border: "0.5px solid rgba(0,0,0,0.12)",
            borderRadius: 6,
            padding: "5px 14px",
            cursor: "pointer",
            width: "100%",
          }}
        >
          Show {Math.min(PAGE_SIZE, data.length - visible)} more
          <span style={{ color: "#9b9b9b", marginLeft: 4 }}>({data.length - visible} remaining)</span>
        </button>
      )}
    </div>
  );
}

function TabBar({ tabs, active, onChange }) {
  return (
    <div style={{ display: "flex", gap: 0, borderBottom: "0.5px solid rgba(0,0,0,0.10)", marginBottom: 20 }}>
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          style={{
            padding: "8px 16px",
            fontSize: 13,
            fontWeight: 500,
            color: active === tab.id ? "#378add" : "#6b6b6b",
            background: "none",
            border: "none",
            borderBottom: active === tab.id ? "2px solid #378add" : "2px solid transparent",
            cursor: "pointer",
            marginBottom: -1,
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function Citations() {
  const { days } = useFilter();
  const [mentionCitations, setMentionCitations] = useState([]);
  const [sentimentCitations, setSentimentCitations] = useState([]);
  const [qcCitations, setQcCitations] = useState([]);
  const [mentionSchool, setMentionSchool] = useState("All");
  const [sentimentSchool, setSentimentSchool] = useState("All");
  const [activeTab, setActiveTab] = useState("about");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    Promise.all([
      fetch(`${API_BASE_URL}/api/citations-by-school?${params}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/sentiment-citations?${params}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/qc-citations?${params}`).then(r => r.json()),
    ])
      .then(([mentionData, sentimentData, qcData]) => {
        setMentionCitations(mentionData);
        setSentimentCitations(sentimentData);
        setQcCitations(qcData);
        setLoading(false);
      })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [days]);

  if (loading) return <p className="state-msg">Loading...</p>;
  if (error)   return <p className="state-msg state-msg--error">Error: {error}</p>;

  const filterData = (data, school) => {
    const filtered = school === "All" ? data : data.filter(c => c.school === school);
    const sorted = [...filtered].sort((a, b) => b.count - a.count);
    return {
      qc:       sorted.filter(c => c.source_type === "QC owned"),
      external: sorted.filter(c => c.source_type === "external").slice(0, 20),
    };
  };

  const mentionFiltered   = filterData(mentionCitations, mentionSchool);
  const sentimentFiltered = filterData(sentimentCitations, sentimentSchool);
  const qcTotal           = qcCitations.reduce((sum, c) => sum + c.count, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div className="metric-card">
          <p className="metric-label">QC pages cited (total)</p>
          <p className="metric-value">{qcTotal.toLocaleString()}</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">Unique QC pages cited</p>
          <p className="metric-value">{qcCitations.length}</p>
        </div>
      </div>

      {/* All QC pages */}
      <div className="card">
        <p className="panel-title">All QC pages cited</p>
        <p className="panel-subtitle">Every QC-owned URL appearing as a source across all AI responses</p>
        <CitationList data={qcCitations} color="#378add" emptyMsg="No QC citations recorded yet." />
      </div>

      {/* Sources breakdown by tab */}
      <div className="card">
        <TabBar
          tabs={[
            { id: "about",     label: "About QC" },
            { id: "discovery", label: "Course discovery" },
          ]}
          active={activeTab}
          onChange={setActiveTab}
        />

        {activeTab === "about" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p className="panel-title">Sources used when AI answers questions about QC</p>
                <p className="panel-subtitle">From credibility and competition questions — these directly shape QC's reputation</p>
              </div>
              <SchoolFilter value={sentimentSchool} onChange={setSentimentSchool} />
            </div>

            {sentimentFiltered.qc.length > 0 && (
              <div>
                <p style={{ fontSize: 12, fontWeight: 500, color: "#6b6b6b", marginBottom: 10 }}>QC owned</p>
                <CitationList data={sentimentFiltered.qc} color="#378add" />
              </div>
            )}

            <div>
              <p style={{ fontSize: 12, fontWeight: 500, color: "#6b6b6b", marginBottom: 4 }}>External</p>
              <p style={{ fontSize: 11, color: "#9b9b9b", marginBottom: 10 }}>Review sites, Reddit threads, competitor pages shaping AI's view of QC</p>
              <CitationList data={sentimentFiltered.external} color="#a32d2d" emptyMsg="No external sources found." />
            </div>
          </div>
        )}

        {activeTab === "discovery" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p className="panel-title">Sources used when AI recommends courses generally</p>
                <p className="panel-subtitle">From course and general questions — what QC is competing against for visibility</p>
              </div>
              <SchoolFilter value={mentionSchool} onChange={setMentionSchool} />
            </div>

            {mentionFiltered.qc.length > 0 && (
              <div>
                <p style={{ fontSize: 12, fontWeight: 500, color: "#6b6b6b", marginBottom: 10 }}>QC owned</p>
                <CitationList data={mentionFiltered.qc} color="#378add" />
              </div>
            )}

            <div>
              <p style={{ fontSize: 12, fontWeight: 500, color: "#6b6b6b", marginBottom: 4 }}>External</p>
              <p style={{ fontSize: 11, color: "#9b9b9b", marginBottom: 10 }}>Course aggregators, competitor pages, job boards cited instead of QC</p>
              <CitationList data={mentionFiltered.external} color="#7c3aed" emptyMsg="No external sources found." />
            </div>
          </div>
        )}
      </div>

    </div>
  );
}

export default Citations;