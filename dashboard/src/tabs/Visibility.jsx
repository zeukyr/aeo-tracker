import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList
} from "recharts";
import { API_BASE_URL } from "../config";

function Visibility() {
  const [mentionCategoryData, setMentionCategoryData] = useState([]);
  const [citationCategoryData, setCitationCategoryData] = useState([]);
  const [mentionSchoolData, setMentionSchoolData] = useState([]);
  const [citationSchoolData, setCitationSchoolData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE_URL}/api/mention-rate-by-category`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/mention-rate-by-school`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/citation-rate-by-category`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/citation-rate-by-school`).then(r => r.json())
    ])
      .then(([mentionCategoryData, mentionSchoolData, citationCategoryData, citationSchoolData]) => {
        setMentionCategoryData(mentionCategoryData);
        setMentionSchoolData(mentionSchoolData);
        setCitationCategoryData(citationCategoryData);
        setCitationSchoolData(citationSchoolData);
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
        <p className="font-medium mb-3">Mention rate by question category</p>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={mentionCategoryData} layout="vertical">
            <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} />
            <YAxis type="category" dataKey="category" width={110} />
            <Tooltip formatter={v => `${v}%`} />
            <Bar dataKey="mention_rate" fill="#2563eb" radius={[0, 4, 4, 0]}>
              <LabelList dataKey="mention_rate" position="right" formatter={v => `${v}%`} style={{ fontSize: 13 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-3">Mention rate by school</p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={mentionSchoolData} layout="vertical">
            <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} />
            <YAxis type="category" dataKey="school" width={160} />
            <Tooltip formatter={v => `${v}%`} />
            <Bar dataKey="mention_rate" fill="#16a34a" radius={[0, 4, 4, 0]}>
              <LabelList dataKey="mention_rate" position="right" formatter={v => `${v}%`} style={{ fontSize: 13 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-3">Citation rate by question category</p>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={citationCategoryData} layout="vertical">
            <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} />
            <YAxis type="category" dataKey="category" width={110} />
            <Tooltip formatter={v => `${v}%`} />
            <Bar dataKey="mention_rate" fill="#2563eb" radius={[0, 4, 4, 0]}>
              <LabelList dataKey="mention_rate" position="right" formatter={v => `${v}%`} style={{ fontSize: 13 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="font-medium mb-3">Citation rate by school</p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={citationSchoolData} layout="vertical">
            <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} />
            <YAxis type="category" dataKey="school" width={160} />
            <Tooltip formatter={v => `${v}%`} />
            <Bar dataKey="mention_rate" fill="#16a34a" radius={[0, 4, 4, 0]}>
              <LabelList dataKey="mention_rate" position="right" formatter={v => `${v}%`} style={{ fontSize: 13 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default Visibility;