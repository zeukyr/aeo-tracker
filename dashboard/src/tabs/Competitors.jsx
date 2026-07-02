import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import { CompetitorWinRate } from "./CompetitorWinRate";

const ALL_SCHOOLS = [
  "All",
  "QC Pet Studies",
  "QC Event Planning",
  "QC Design School",
  "QC Makeup Academy",
  "QC Wellness Studies",
];

const PURPLE = "#7c3aed";

function CompetitorRow({ rank, name, count, maxCount }) {
  const pct = Math.round((count / maxCount) * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <span style={{
        width: 20, textAlign: "right",
        fontSize: 12, color: "#9b9b9b", flexShrink: 0,
      }}>
        {rank}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
          <span style={{ fontSize: 13, color: "#111", fontWeight: rank === 1 ? 500 : 400 }}>{name}</span>
          <span style={{ fontSize: 12, color: "#6b6b6b", flexShrink: 0, marginLeft: 8 }}>{count}</span>
        </div>
        <div style={{ height: 5, background: "#f0efec", borderRadius: 99, overflow: "hidden" }}>
          <div style={{
            height: "100%",
            width: `${pct}%`,
            background: PURPLE,
            opacity: 0.4 + 0.6 * (count / maxCount),
            borderRadius: 99,
            transition: "width 0.4s ease",
          }} />
        </div>
      </div>
    </div>
  );
}

function Competitors() {
  const { days, school } = useFilter();
  const [competitorsBySchool, setCompetitorsBySchool] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState("All");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);
    if (school && school !== "All") params.append("school", school);

    fetch(`${API_BASE_URL}/api/top-competitors-by-school?${params}`)
      .then(r => r.json())
      .then(data => {
        setCompetitorsBySchool(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [days, school]);

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
              {selectedSchool === "All"
                ? "Across all schools"
                : `In ${selectedSchool} questions`}
            </p>
          </div>
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