import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";

const PRIORITY_STYLES = {
  high: "bg-red-100 text-red-700 border-red-200",
  medium: "bg-yellow-100 text-yellow-700 border-yellow-200",
  low: "bg-gray-100 text-gray-600 border-gray-200",
};

const STATUS_OPTIONS = ["pending", "in_progress", "done"];

function RecommendationCard({ rec, onStatusChange }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs font-medium px-2 py-0.5 rounded border ${PRIORITY_STYLES[rec.priority] || PRIORITY_STYLES.low}`}>
            {rec.priority}
          </span>
          {rec.school && (
            <span className="text-xs text-gray-500 bg-gray-50 px-2 py-0.5 rounded">
              {rec.school}
            </span>
          )}
        </div>
        <select
          className="text-xs border border-gray-200 rounded px-2 py-1"
          value={rec.status}
          onChange={e => onStatusChange(rec.id, e.target.value)}
        >
          {STATUS_OPTIONS.map(s => (
            <option key={s} value={s}>{s.replace("_", " ")}</option>
          ))}
        </select>
      </div>

      <p className="font-medium text-sm mb-1">{rec.problem}</p>
      <p className="text-sm text-gray-600 mb-2">{rec.action}</p>

      {rec.evidence && (
        <button
          className="text-xs text-blue-600 hover:underline"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? "Hide evidence" : "Show evidence"}
        </button>
      )}

      {expanded && (
        <p className="text-xs text-gray-500 mt-2 bg-gray-50 rounded p-2">
          {rec.evidence}
        </p>
      )}
    </div>
  );
}

function Recommendations() {
  const { days } = useFilter();
  const [recommendations, setRecommendations] = useState([]);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [filterStatus, setFilterStatus] = useState("All");
  const [filterPriority, setFilterPriority] = useState("All");

  const loading = recommendations === null && error === null;

  const loadRecommendations = () => {
    fetch(`${API_BASE_URL}/api/recommendations`)
      .then(r => r.json())
      .then(data => setRecommendations(data))
      .catch(err => setError(err.message));
  };

  useEffect(() => {
    loadRecommendations();
  }, []);

  const handleGenerate = () => {
    setGenerating(true);
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/generate-recommendations?${params}`)
      .then(r => r.json())
      .then(() => {
        loadRecommendations();
        setGenerating(false);
      })
      .catch(err => {
        setError(err.message);
        setGenerating(false);
      });
  };

const handleStatusChange = (id, newStatus) => {
  setRecommendations(prev =>
    prev.map(r => (r.id === id ? { ...r, status: newStatus } : r))
  );
  fetch(`${API_BASE_URL}/api/recommendations/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: newStatus })
  }).catch(err => console.error("Failed to update status:", err));
};


    if (error) return <p className="text-red-600">Error: {error}</p>;
  if (loading) return <p className="text-gray-500">Loading...</p>;

  const filtered = recommendations.filter(r => {
    if (filterStatus !== "All" && r.status !== filterStatus) return false;
    if (filterPriority !== "All" && r.priority !== filterPriority) return false;
    return true;
  });

  const priorityOrder = { high: 0, medium: 1, low: 2 };
  const sorted = [...filtered].sort(
    (a, b) => (priorityOrder[a.priority] ?? 3) - (priorityOrder[b.priority] ?? 3)
  );

  return (
    <div className="space-y-4">
      <div className="bg-white border border-gray-200 rounded-lg p-4 flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="font-medium">AI-generated recommendations</p>
          <p className="text-sm text-gray-500">
            Based on competitor wins, citation gaps, and recurring concerns from the selected period
          </p>
        </div>
        <button
          className="text-sm bg-blue-600 text-white rounded px-3 py-1.5 disabled:opacity-50"
          onClick={handleGenerate}
          disabled={generating}
        >
          {generating ? "Generating..." : "Generate new recommendations"}
        </button>
      </div>

      <div className="flex gap-3">
        <select
          className="text-sm border border-gray-200 rounded px-2 py-1"
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
        >
          <option value="All">All statuses</option>
          {STATUS_OPTIONS.map(s => (
            <option key={s} value={s}>{s.replace("_", " ")}</option>
          ))}
        </select>
        <select
          className="text-sm border border-gray-200 rounded px-2 py-1"
          value={filterPriority}
          onChange={e => setFilterPriority(e.target.value)}
        >
          <option value="All">All priorities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {sorted.length === 0 ? (
        <p className="text-gray-400 text-sm">
          No recommendations yet. Click "Generate new recommendations" to analyze the current data.
        </p>
      ) : (
        <div className="space-y-3">
          {sorted.map(rec => (
            <RecommendationCard
              key={rec.id}
              rec={rec}
              onStatusChange={handleStatusChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default Recommendations;