import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

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
      <p style={{ color: "#6b6b6b", marginBottom: 6, fontSize: 12 }}>{label}</p>
      {payload.map(p => (
        <p key={p.name} style={{ color: p.color, fontWeight: 500, margin: "2px 0" }}>
          {p.name}: {p.value}%
        </p>
      ))}
    </div>
  );
}

export function SentimentTrendChart({ data }) {
  return (
    <>
      <div style={{ display: "flex", gap: 14, marginBottom: 12, flexWrap: "wrap" }}>
        {[
          { label: "Positive", color: "#3b6d11" },
          { label: "Neutral",  color: "#854f0b" },
          { label: "Negative", color: "#a32d2d" },
        ].map(({ label, color }) => (
          <span key={label} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "#6b6b6b" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
            {label}
          </span>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gradPos" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#3b6d11" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#3b6d11" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradNeu" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#854f0b" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#854f0b" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradNeg" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#a32d2d" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#a32d2d" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="day"
            tick={{ fontSize: 11, fill: "#888780" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={v => `${v}%`}
            tick={{ fontSize: 11, fill: "#888780" }}
            axisLine={false}
            tickLine={false}
            width={36}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area type="monotone" dataKey="positive" stroke="#3b6d11" strokeWidth={2} fill="url(#gradPos)" name="Positive" dot={false} />
          <Area type="monotone" dataKey="neutral"  stroke="#854f0b" strokeWidth={2} fill="url(#gradNeu)" name="Neutral"  dot={false} />
          <Area type="monotone" dataKey="negative" stroke="#a32d2d" strokeWidth={2} fill="url(#gradNeg)" name="Negative" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </>
  );
}
