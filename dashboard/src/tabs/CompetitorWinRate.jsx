import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";

const RED = "#a32d2d";
const RED_BG = "#fcebeb";

function WinRateRow({ rank, competitor, winRate }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <span style={{ width: 20, textAlign: "right", fontSize: 12, color: "#9b9b9b", flexShrink: 0 }}>
        {rank}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
          <span style={{ fontSize: 13, color: "#111" }}>{competitor}</span>
          <span style={{
            fontSize: 11, fontWeight: 500,
            background: winRate > 50 ? RED_BG : "#eaf3de",
            color: winRate > 50 ? RED : "#3b6d11",
            padding: "2px 7px", borderRadius: 99,
          }}>
            {winRate}%
          </span>
        </div>
        <div style={{ height: 5, background: "#f0efec", borderRadius: 99, overflow: "hidden" }}>
          <div style={{
            height: "100%",
            width: `${winRate}%`,
            background: winRate > 50 ? RED : "#1d9e75",
            borderRadius: 99,
            transition: "width 0.4s ease",
          }} />
        </div>
      </div>
    </div>
  );
}

export function CompetitorWinRate() {
  const { days } = useFilter();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/competitor-win-rate?${params}`)
      .then(r => r.json())
      .then(data => { setData(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [days]);

  if (loading) return <p className="state-msg">Loading...</p>;
  if (!data.length) return <p className="state-empty">No competition data yet.</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}>
      {data.map((d, i) => (
        <WinRateRow key={d.competitor} rank={i + 1} competitor={d.competitor} winRate={d.win_rate} />
      ))}
    </div>
  );
}