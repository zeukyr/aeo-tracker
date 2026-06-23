import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";

function DiffBadge({ diff }) {
  if (diff === null || diff === undefined) return <p className="text-xs text-gray-400">No previous data</p>;
  if (diff === 0) return <p className="text-xs text-gray-400">— No change vs previous period</p>;
  const positive = diff > 0;
  return (
    <p className={`text-xs font-medium ${positive ? "text-green-600" : "text-red-500"}`}>
      {positive ? "↑" : "↓"} {Math.abs(diff)}% vs previous period
    </p>
  );
}

function MetricCard({ label, value, diff }) {
  return (
    <div className="bg-gray-50 rounded-md p-4">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-medium mb-1">{value}</p>
      <DiffBadge diff={diff} />
    </div>
  );
}

function Overview() {
  const { days } = useFilter();
  const [mentionData, setMentionData] = useState([]);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  const loading = summary === null && error === null;

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    Promise.all([
      fetch(`${API_BASE_URL}/api/mention-rate-by-engine?${params}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/summary?${params}`).then(r => r.json())
    ])
      .then(([mentionData, summaryData]) => {
        setMentionData(mentionData);
        setSummary(summaryData);
      })
      .catch(err => setError(err.message));
  }, [days]);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <MetricCard
          label="Mention rate"
          value={`${summary.mention_rate}%`}
          diff={summary.mention_rate_diff}
        />
        <MetricCard
          label="Positive sentiment"
          value={`${summary.positive_sentiment_rate}%`}
          diff={summary.positive_sentiment_diff}
        />
        <MetricCard
          label="Top competitor"
          value={summary.top_competitor || "--"}
          diff={null}
        />
        <MetricCard
          label="Best engine"
          value={summary.best_engine || "--"}
          diff={null}
        />
        <MetricCard
          label="Cited QC"
          value={summary.citation_rate ? `${summary.citation_rate}%` : "--"}
          diff={summary.citation_rate_diff}
        />
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-3">Mention rate by engine</p>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={mentionData}>
            <XAxis dataKey="day" />
            <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} />
            <Tooltip formatter={v => `${v}%`} />
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