import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer
} from "recharts";
import { API_BASE_URL } from "../config";

function Overview() {
  const [mentionData, setMentionData] = useState([]);
  const [citationData, setCitationData] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE_URL}/api/mention-rate-by-engine`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/citation-rate-by-engine`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/summary`).then(r => r.json())
    ])
      .then(([mentionData, citationData, summaryData]) => {
        setMentionData(mentionData);
        setCitationData(citationData);
        setSummary(summaryData);
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
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <div className="bg-gray-50 rounded-md p-4">
          <p className="text-sm text-gray-500 mb-1">Mention rate</p>
          <p className="text-2xl font-medium">{summary.mention_rate}%</p>
        </div>
        <div className="bg-gray-50 rounded-md p-4">
          <p className="text-sm text-gray-500 mb-1">Citation rate</p>
          <p className="text-2xl font-medium">{summary.citation_rate}%</p>
        </div>
        <div className="bg-gray-50 rounded-md p-4">
          <p className="text-sm text-gray-500 mb-1">Positive sentiment</p>
          <p className="text-2xl font-medium">{summary.positive_sentiment_rate}%</p>
        </div>
        <div className="bg-gray-50 rounded-md p-4">
          <p className="text-sm text-gray-500 mb-1">Top competitor</p>
          <p className="text-2xl font-medium">{summary.top_competitor || "--"}</p>
        </div>
        <div className="bg-gray-50 rounded-md p-4">
          <p className="text-sm text-gray-500 mb-1">Best engine</p>
          <p className="text-2xl font-medium">{summary.best_engine || "--"}</p>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-3">Mention rate by engine</p>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={mentionData}>
            <XAxis dataKey="day" />
            <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
            <Tooltip formatter={(value) => `${value}%`} />
            <Legend />
            <Line type="monotone" dataKey="chatgpt" stroke="#2563eb" name="ChatGPT" dot={true} />
            <Line type="monotone" dataKey="perplexity" stroke="#16a34a" name="Perplexity" dot={true} />
            <Line type="monotone" dataKey="gemini" stroke="#d97706" name="Gemini" dot={true} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-3">Citation rate by engine</p>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={citationData}>
            <XAxis dataKey="day" />
            <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
            <Tooltip formatter={(value) => `${value}%`} />
            <Legend />
            <Line type="monotone" dataKey="chatgpt" stroke="#2563eb" name="ChatGPT" dot={true} />
            <Line type="monotone" dataKey="perplexity" stroke="#16a34a" name="Perplexity" dot={true} />
            <Line type="monotone" dataKey="gemini" stroke="#d97706" name="Gemini" dot={true} />
          </LineChart>
        </ResponsiveContainer>

      </div>
    </div>
  );
}

export default Overview;