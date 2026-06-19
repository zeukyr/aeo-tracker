import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList
} from "recharts";
import { API_BASE_URL } from "../config";

function Competitors() {
  const [competitors, setCompetitors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/top-competitors`)
      .then(r => r.json())
      .then(data => {
        setCompetitors(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;

  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-3">Top competitors mentioned</p>
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={competitors} layout="vertical">
            <XAxis type="number" />
            <YAxis type="category" dataKey="competitor" width={160} />
            <Tooltip />
            <Bar dataKey="count" fill="#7c3aed" radius={[0, 4, 4, 0]}>
              <LabelList dataKey="count" position="right" style={{ fontSize: 13 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-1">Competitor win rate</p>
        <p className="text-sm text-gray-500 mb-3">How often each competitor is recommended over QC in direct comparison questions</p>
        <CompetitorWinRate />
      </div>
    </div>
  );
}

function CompetitorWinRate() {
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

export default Competitors;