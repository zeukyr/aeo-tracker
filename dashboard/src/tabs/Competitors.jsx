import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList
} from "recharts";
import { API_BASE_URL } from "../config";
import { CompetitorWinRate } from "./CompetitorWinRate";

const ALL_SCHOOLS = [
  "All",
  "QC Pet Studies",
  "QC Event Planning",
  "QC Design School",
  "QC Makeup Academy",
  "QC Wellness Studies"
];

function Competitors() {
  const [competitorsBySchool, setCompetitorsBySchool] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState("All");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/top-competitors-by-school`)
      .then(r => r.json())
      .then(data => {
        setCompetitorsBySchool(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;

  const filteredBySchool = selectedSchool === "All"
    ? competitorsBySchool
    : competitorsBySchool.filter(c => c.school === selectedSchool);

  const aggregated = Object.values(
    filteredBySchool.reduce((acc, c) => {
      if (!acc[c.competitor]) acc[c.competitor] = { competitor: c.competitor, count: 0 };
      acc[c.competitor].count += c.count;
      return acc;
    }, {})
  ).sort((a, b) => b.count - a.count).slice(0, 10);

  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="flex items-center justify-between mb-1">
          <p className="font-medium mb-3">Top competitors mentioned</p>
          <select
              className="text-sm border border-gray-200 rounded px-2 py-1"
              value={selectedSchool}
              onChange={e => setSelectedSchool(e.target.value)}
          >
              {ALL_SCHOOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <p className="text-sm text-gray-500 mb-3">
          {selectedSchool === "All"
            ? "Competitors mentioned across all schools"
            : `Competitors mentioned in ${selectedSchool} questions`}
        </p>
        <ResponsiveContainer width="100%" height={350}>
          <BarChart data={aggregated} layout="vertical">
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

export default Competitors;