import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList, Cell
} from "recharts";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";

const BLUE  = "#378add";
const GREEN = "#1d9e75";

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#fff",
      border: "0.5px solid rgba(0,0,0,0.10)",
      borderRadius: 8,
      padding: "8px 12px",
      fontSize: 13,
      boxShadow: "0 2px 8px rgba(0,0,0,0.08)"
    }}>
      <p style={{ color: "#6b6b6b", marginBottom: 2 }}>{label}</p>
      <p style={{ fontWeight: 500, color: "#111" }}>{payload[0].value}%</p>
    </div>
  );
}

function HorizontalBarChart({ data, dataKey, labelKey, color, height }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 0, right: 40, top: 4, bottom: 4 }}>
        <XAxis
          type="number"
          domain={[0, 100]}
          tickFormatter={v => `${v}%`}
          tick={{ fontSize: 11, fill: "#888780" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey={labelKey}
          width={130}
          tick={{ fontSize: 12, fill: "#6b6b6b" }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
        <Bar dataKey={dataKey} radius={[0, 4, 4, 0]} maxBarSize={20}>
          {data.map((_, i) => (
            <Cell key={i} fill={color} fillOpacity={1 - i * 0.08 > 0.4 ? 1 - i * 0.08 : 0.4} />
          ))}
          <LabelList
            dataKey={dataKey}
            position="right"
            formatter={v => `${v}%`}
            style={{ fontSize: 12, fill: "#6b6b6b", fontWeight: 500 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function ChartPanel({ title, subtitle, children }) {
  return (
    <div className="card">
      <p className="panel-title">{title}</p>
      {subtitle && <p className="panel-subtitle">{subtitle}</p>}
      {children}
    </div>
  );
}

function Visibility() {
  const { days } = useFilter();
  const [mentionCategoryData, setMentionCategoryData] = useState([]);
  const [citationCategoryData, setCitationCategoryData] = useState([]);
  const [mentionSchoolData, setMentionSchoolData] = useState([]);
  const [citationSchoolData, setCitationSchoolData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    Promise.all([
      fetch(`${API_BASE_URL}/api/mention-rate-by-category?${params}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/mention-rate-by-school?${params}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/citation-rate-by-category?${params}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/citation-rate-by-school?${params}`).then(r => r.json()),
    ])
      .then(([mentionCat, mentionSchool, citationCat, citationSchool]) => {
        setMentionCategoryData(mentionCat);
        setMentionSchoolData(mentionSchool);
        setCitationCategoryData(citationCat);
        setCitationSchoolData(citationSchool);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [days]);

  if (loading) return <p className="state-msg">Loading...</p>;
  if (error)   return <p className="state-msg state-msg--error">Error: {error}</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <ChartPanel
          title="Mention rate by category"
          subtitle="How often QC appears per question type"
        >
          <HorizontalBarChart
            data={mentionCategoryData}
            dataKey="mention_rate"
            labelKey="category"
            color={BLUE}
            height={Math.max(180, mentionCategoryData.length * 48)}
          />
        </ChartPanel>

        <ChartPanel
          title="Citation rate by category"
          subtitle="How often QC is cited per question type"
        >
          <HorizontalBarChart
            data={citationCategoryData}
            dataKey="mention_rate"
            labelKey="category"
            color={GREEN}
            height={Math.max(180, citationCategoryData.length * 48)}
          />
        </ChartPanel>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <ChartPanel
          title="Mention rate by school"
          subtitle="QC vs competitors across all questions"
        >
          <HorizontalBarChart
            data={mentionSchoolData}
            dataKey="mention_rate"
            labelKey="school"
            color={BLUE}
            height={Math.max(180, mentionSchoolData.length * 48)}
          />
        </ChartPanel>

        <ChartPanel
          title="Citation rate by school"
          subtitle="Source link frequency per school"
        >
          <HorizontalBarChart
            data={citationSchoolData}
            dataKey="mention_rate"
            labelKey="school"
            color={GREEN}
            height={Math.max(180, citationSchoolData.length * 48)}
          />
        </ChartPanel>
      </div>

    </div>
  );
}

export default Visibility;