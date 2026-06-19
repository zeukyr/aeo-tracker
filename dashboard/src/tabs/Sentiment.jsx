import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList,
  AreaChart, Area, Legend
} from "recharts";
import { API_BASE_URL } from "../config";

function Sentiment() {
  const [sentimentData, setSentimentData] = useState([]);
  const [concerns, setConcerns] = useState([]);
  const [positives, setPositives] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE_URL}/api/sentiment-distribution`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/top-concerns`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/top-positives`).then(r => r.json())
    ])
      .then(([sentimentData, concerns, positives]) => {
        setSentimentData(sentimentData);
        setConcerns(concerns);
        setPositives(positives);
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
        <p className="font-medium mb-3">Sentiment over time</p>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={sentimentData}>
            <XAxis dataKey="day" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Area type="monotone" dataKey="positive" stackId="1" stroke="#16a34a" fill="#bbf7d0" name="Positive" />
            <Area type="monotone" dataKey="neutral" stackId="1" stroke="#d97706" fill="#fde68a" name="Neutral" />
            <Area type="monotone" dataKey="negative" stackId="1" stroke="#dc2626" fill="#fecaca" name="Negative" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="font-medium mb-3">Top concerns raised</p>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={concerns} layout="vertical">
              <XAxis type="number" />
              <YAxis type="category" dataKey="concern" width={160} />
              <Tooltip />
              <Bar dataKey="count" fill="#dc2626" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="count" position="right" style={{ fontSize: 13 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="font-medium mb-3">Top positives raised</p>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={positives} layout="vertical">
              <XAxis type="number" />
              <YAxis type="category" dataKey="positive" width={160} />
              <Tooltip />
              <Bar dataKey="count" fill="#16a34a" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="count" position="right" style={{ fontSize: 13 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

export default Sentiment;