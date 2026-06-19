import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList, Cell
} from "recharts";
import { API_BASE_URL } from "../config";

function Citations() {
  const [citations, setCitations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/citations`)
      .then(r => r.json())
      .then(data => {
        setCitations(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;

  const qcCitations = citations.filter(c => c.source_type === "QC owned");
  const externalCitations = citations.filter(c => c.source_type === "external");

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 mb-2">
        <div className="bg-gray-50 rounded-md p-4">
          <p className="text-sm text-gray-500 mb-1">QC owned citations</p>
          <p className="text-2xl font-medium">{qcCitations.reduce((sum, c) => sum + c.count, 0)}</p>
        </div>
        <div className="bg-gray-50 rounded-md p-4">
          <p className="text-sm text-gray-500 mb-1">External citations</p>
          <p className="text-2xl font-medium">{externalCitations.reduce((sum, c) => sum + c.count, 0)}</p>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-1">QC owned pages cited</p>
        <p className="text-sm text-gray-500 mb-3">QC's own URLs appearing as sources in AI responses</p>
        {qcCitations.length === 0 ? (
          <p className="text-gray-400 text-sm">No QC pages cited yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(200, qcCitations.length * 50)}>
            <BarChart data={qcCitations} layout="vertical">
              <XAxis type="number" />
              <YAxis type="category" dataKey="url" width={260} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#2563eb" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="count" position="right" style={{ fontSize: 13 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-1">Top external domains cited</p>
        <p className="text-sm text-gray-500 mb-3">Non-QC sources AI engines are pulling from — competitors, review sites, job boards</p>
        <ResponsiveContainer width="100%" height={Math.max(200, externalCitations.length * 40)}>
          <BarChart data={externalCitations} layout="vertical">
            <XAxis type="number" />
            <YAxis type="category" dataKey="url" width={260} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey="count" radius={[0, 4, 4, 0]}>
              {externalCitations.map((entry, index) => (
                <Cell key={index} fill={index % 2 === 0 ? "#7c3aed" : "#a78bfa"} />
              ))}
              <LabelList dataKey="count" position="right" style={{ fontSize: 13 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default Citations;