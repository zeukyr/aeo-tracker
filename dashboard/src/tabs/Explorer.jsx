import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";

const ENGINES = ["All", "chatgpt", "perplexity", "gemini"];
const TYPES = ["All", "course", "general", "credibility", "competition"];
const SCHOOLS = ["All", "QC Pet Studies", "QC Event Planning", "QC Design School", "QC Makeup Academy", "QC Wellness Studies"];
const SENTIMENTS = ["All", "positive", "neutral", "negative"];
const DAYS_OPTIONS = [
  { label: "All time", value: "" },
  { label: "Last 7 days", value: "7" },
  { label: "Last 30 days", value: "30" },
  { label: "Last 90 days", value: "90" },
];

function FilterSelect({ label, value, onChange, options }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-gray-500">{label}</label>
      <select
        className="text-sm border border-gray-200 rounded px-2 py-1"
        value={value}
        onChange={e => onChange(e.target.value)}
      >
        {options.map(o => (
          <option key={typeof o === "string" ? o : o.value} value={typeof o === "string" ? o : o.value}>
            {typeof o === "string" ? o : o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function ResponseRow({ row }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr
        className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="py-3 px-4 text-sm max-w-xs truncate">{row.question}</td>
        <td className="py-3 px-4 text-sm capitalize">{row.engine}</td>
        <td className="py-3 px-4 text-sm">{row.school || "--"}</td>
        <td className="py-3 px-4 text-sm">{row.question_type}</td>
        <td className="py-3 px-4 text-sm">
          {row.qc_mentioned !== null
            ? <span className={`px-2 py-0.5 rounded text-xs ${row.qc_mentioned === "true" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                {row.qc_mentioned === "true" ? "Yes" : "No"}
              </span>
            : row.qc_sentiment
              ? <span className={`px-2 py-0.5 rounded text-xs ${
                  row.qc_sentiment === "positive" ? "bg-green-100 text-green-700"
                  : row.qc_sentiment === "negative" ? "bg-red-100 text-red-700"
                  : "bg-yellow-100 text-yellow-700"
                }`}>
                  {row.qc_sentiment}
                </span>
              : "--"
          }
        </td>
        <td className="py-3 px-4 text-sm text-gray-400">{row.created_at.slice(0, 10)}</td>
        <td className="py-3 px-4 text-sm text-gray-400">{expanded ? "▲" : "▼"}</td>
      </tr>
      {expanded && (
        <tr className="bg-gray-50">
          <td colSpan={7} className="px-4 py-3">
            <p className="text-xs text-gray-500 mb-1">Full response</p>
            <p className="text-sm whitespace-pre-wrap text-gray-700">{row.raw_response}</p>
          </td>
        </tr>
      )}
    </>
  );
}

function Explorer() {
  const [data, setData] = useState({ results: [], total: 0, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    days: "",
    engine: "All",
    question_type: "All",
    school: "All",
    qc_mentioned: "All",
    sentiment: "All",
    page: 1,
    });

  const setFilter = (key, value) => {
    setFilters(f => ({ ...f, [key]: value, page: 1 }));
  };

  const setPage = (newPage) => {
    setFilters(f => ({ ...f, page: newPage }));
};

useEffect(() => {
  const params = new URLSearchParams();
  if (filters.days) params.append("days", filters.days);
  if (filters.engine !== "All") params.append("engine", filters.engine);
  if (filters.question_type !== "All") params.append("question_type", filters.question_type);
  if (filters.school !== "All") params.append("school", filters.school);
  if (filters.qc_mentioned !== "All") params.append("qc_mentioned", filters.qc_mentioned === "Yes");
  if (filters.sentiment !== "All") params.append("sentiment", filters.sentiment);
  params.append("page", filters.page);

  fetch(`${API_BASE_URL}/api/responses?${params.toString()}`)
    .then(r => r.json())
    .then(data => {
      setData(data);
      setLoading(false);
    })
    .catch(err => {
      setError(err.message);
      setLoading(false);
    });
}, [filters]);

  if (error) return <p className="text-red-600">Error: {error}</p>;

  return (
    <div className="space-y-4">
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-3">Filters</p>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <FilterSelect label="Date range" value={filters.days} onChange={v => setFilter("days", v)} options={DAYS_OPTIONS} />
          <FilterSelect label="Engine" value={filters.engine} onChange={v => setFilter("engine", v)} options={ENGINES} />
          <FilterSelect label="Question type" value={filters.question_type} onChange={v => setFilter("question_type", v)} options={TYPES} />
          <FilterSelect label="School" value={filters.school} onChange={v => setFilter("school", v)} options={SCHOOLS} />
          <FilterSelect label="QC mentioned" value={filters.qc_mentioned} onChange={v => setFilter("qc_mentioned", v)} options={["All", "Yes", "No"]} />
          <FilterSelect label="Sentiment" value={filters.sentiment} onChange={v => setFilter("sentiment", v)} options={SENTIMENTS} />
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <p className="text-sm text-gray-500">{data.total} responses</p>
        </div>

        {loading ? (
          <p className="text-gray-500 p-4">Loading...</p>
        ) : data.results.length === 0 ? (
          <p className="text-gray-400 p-4">No responses match your filters.</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="py-2 px-4 text-left text-xs text-gray-500 font-medium">Question</th>
                <th className="py-2 px-4 text-left text-xs text-gray-500 font-medium">Engine</th>
                <th className="py-2 px-4 text-left text-xs text-gray-500 font-medium">School</th>
                <th className="py-2 px-4 text-left text-xs text-gray-500 font-medium">Type</th>
                <th className="py-2 px-4 text-left text-xs text-gray-500 font-medium">QC / Sentiment</th>
                <th className="py-2 px-4 text-left text-xs text-gray-500 font-medium">Date</th>
                <th className="py-2 px-4"></th>
              </tr>
            </thead>
            <tbody>
              {data.results.map(row => (
                <ResponseRow key={row.id} row={row} />
              ))}
            </tbody>
          </table>
        )}

        <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
          <button
            className="text-sm text-gray-500 disabled:opacity-30"
            disabled={filters.page === 1}
            onClick={() => setPage(f => f - 1)}
          >
            ← Previous
          </button>
          <p className="text-sm text-gray-500">Page {filters.page} of {data.total_pages}</p>
          <button
            className="text-sm text-gray-500 disabled:opacity-30"
            disabled={filters.page === data.total_pages}
            onClick={() => setPage(p => p + 1)}
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}

export default Explorer;