import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList
} from "recharts";
import { API_BASE_URL } from "../config";

export function CompetitorWinRate() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/competitor-win-rate`)
      .then(r => r.json())
      .then(data => {
        setData(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-400 text-sm">Loading...</p>;
  if (!data.length) return <p className="text-gray-400 text-sm">No competition data yet.</p>;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} layout="vertical">
        <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} />
        <YAxis type="category" dataKey="competitor" width={160} />
        <Tooltip formatter={v => `${v}%`} />
        <Bar dataKey="win_rate" fill="#dc2626" radius={[0, 4, 4, 0]}>
          <LabelList dataKey="win_rate" position="right" formatter={v => `${v}%`} style={{ fontSize: 13 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}