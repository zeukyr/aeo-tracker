import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import { SchoolFilter, CitationList, TabBar, filterData } from "../components/CitationWidgets";

function Citations() {
  const { days, school } = useFilter();
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
    if (school && school !== "All") params.append("school", school);

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
  }, [days, school]);

  if (loading) return <p className="state-msg">Loading...</p>;
  if (error)   return <p className="state-msg state-msg--error">Error: {error}</p>;

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