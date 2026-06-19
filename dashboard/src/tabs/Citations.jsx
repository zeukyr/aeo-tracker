import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList, Cell
} from "recharts";
import { API_BASE_URL } from "../config";

const ALL_SCHOOLS = [
  "All",
  "QC Pet Studies",
  "QC Event Planning",
  "QC Design School",
  "QC Makeup Academy",
  "QC Wellness Studies"
];

function CitationChart({ data, color = "#7c3aed" }) {
  if (!data.length) return <p className="text-gray-400 text-sm">No data for this selection.</p>;
  return (
    <ResponsiveContainer width="100%" height={Math.max(200, data.length * 40)}>
      <BarChart data={data} layout="vertical">
        <XAxis type="number" />
        <YAxis type="category" dataKey="url" width={300} tick={{ fontSize: 11 }} />
        <Tooltip />
        <Bar dataKey="count" radius={[0, 4, 4, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={i % 2 === 0 ? color : `${color}99`} />
          ))}
          <LabelList dataKey="count" position="right" style={{ fontSize: 13 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function SchoolFilter({ value, onChange }) {
  return (
    <select
      className="text-sm border border-gray-200 rounded px-2 py-1"
      value={value}
      onChange={e => onChange(e.target.value)}
    >
      {ALL_SCHOOLS.map(s => <option key={s} value={s}>{s}</option>)}
    </select>
  );
}

function Citations() {
  const [mentionCitations, setMentionCitations] = useState([]);
  const [sentimentCitations, setSentimentCitations] = useState([]);
  const [qcCitations, setQcCitations] = useState([]);
  const [mentionSchool, setMentionSchool] = useState("All");
  const [sentimentSchool, setSentimentSchool] = useState("All");
  const [activeSection, setActiveSection] = useState("about");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE_URL}/api/citations-by-school`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/sentiment-citations`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/qc-citations`).then(r => r.json()),
    ])
      .then(([mentionData, sentimentData, qcData]) => {
        setMentionCitations(mentionData);
        setSentimentCitations(sentimentData);
        setQcCitations(qcData);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;

  const filterData = (data, school) => {
    const filtered = school === "All" ? data : data.filter(c => c.school === school);
    const sorted = [...filtered].sort((a, b) => b.count - a.count);  // if the data is all, needs to be sorted
    return {
      qc: sorted.filter(c => c.source_type === "QC owned"),
      external: sorted.filter(c => c.source_type === "external").slice(0, 20)
    };
  };

  const mentionFiltered = filterData(mentionCitations, mentionSchool);
  const sentimentFiltered = filterData(sentimentCitations, sentimentSchool);
  const qcTotal = qcCitations.reduce((sum, c) => sum + c.count, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-gray-50 rounded-md p-4">
          <p className="text-sm text-gray-500 mb-1">QC pages cited (total)</p>
          <p className="text-2xl font-medium">{qcTotal}</p>
        </div>
        <div className="bg-gray-50 rounded-md p-4">
          <p className="text-sm text-gray-500 mb-1">Unique QC pages cited</p>
          <p className="text-2xl font-medium">{qcCitations.length}</p>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-1">All QC pages cited</p>
        <p className="text-sm text-gray-500 mb-3">Every QC-owned URL appearing as a source across all AI responses</p>
        <CitationChart data={qcCitations} color="#2563eb" />
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="flex gap-4 border-b border-gray-200 mb-4">
          <button
            className={`pb-2 text-sm font-medium ${activeSection === "about" ? "border-b-2 border-blue-600 text-blue-600" : "text-gray-500"}`}
            onClick={() => setActiveSection("about")}
          >
            About QC
          </button>
          <button
            className={`pb-2 text-sm font-medium ${activeSection === "discovery" ? "border-b-2 border-blue-600 text-blue-600" : "text-gray-500"}`}
            onClick={() => setActiveSection("discovery")}
          >
            Course Discovery
          </button>
        </div>

        {activeSection === "about" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Sources used when AI answers questions about QC</p>
                <p className="text-sm text-gray-500">From credibility and competition questions — these directly shape QC's reputation</p>
              </div>
              <SchoolFilter value={sentimentSchool} onChange={setSentimentSchool} />
            </div>

            {sentimentFiltered.qc.length > 0 && (
              <div>
                <p className="text-sm font-medium text-gray-600 mb-2">QC owned sources</p>
                <CitationChart data={sentimentFiltered.qc} color="#2563eb" />
              </div>
            )}

            <div>
              <p className="text-sm font-medium text-gray-600 mb-2">External sources</p>
              <p className="text-xs text-gray-400 mb-2">Review sites, Reddit threads, competitor pages shaping AI's opinion of QC</p>
              <CitationChart data={sentimentFiltered.external} color="#dc2626" />
            </div>
          </div>
        )}

        {activeSection === "discovery" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Sources used when AI recommends courses generally</p>
                <p className="text-sm text-gray-500">From course and general questions — what QC is competing against for visibility</p>
              </div>
              <SchoolFilter value={mentionSchool} onChange={setMentionSchool} />
            </div>

            {mentionFiltered.qc.length > 0 && (
              <div>
                <p className="text-sm font-medium text-gray-600 mb-2">QC owned sources</p>
                <CitationChart data={mentionFiltered.qc} color="#2563eb" />
              </div>
            )}

            <div>
              <p className="text-sm font-medium text-gray-600 mb-2">External sources</p>
              <p className="text-xs text-gray-400 mb-2">Course aggregators, competitor pages, job boards cited instead of QC</p>
              <CitationChart data={mentionFiltered.external} color="#7c3aed" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Citations;