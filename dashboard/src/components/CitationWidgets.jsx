import { useEffect, useState } from "react";

const ALL_SCHOOLS = [
  "All",
  "QC Pet Studies",
  "QC Event Planning",
  "QC Design School",
  "QC Makeup Academy",
  "QC Wellness Studies",
];

export function SchoolFilter({ value, onChange }) {
  return (
    <select
      style={{
        fontSize: 12,
        color: "#6b6b6b",
        border: "0.5px solid rgba(0,0,0,0.15)",
        borderRadius: 6,
        padding: "4px 8px",
        background: "#fff",
        cursor: "pointer",
        flexShrink: 0,
      }}
      value={value}
      onChange={e => onChange(e.target.value)}
    >
      {ALL_SCHOOLS.map(s => <option key={s} value={s}>{s}</option>)}
    </select>
  );
}

export function CitationRow({ rank, url, count, maxCount, color }) {
  const pct = Math.round((count / maxCount) * 100);
  const domain = (() => { try { return new URL(url).hostname.replace("www.", ""); } catch { return url; } })();
  const path   = (() => { try { return new URL(url).pathname; } catch { return ""; } })();

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <span style={{ width: 20, textAlign: "right", fontSize: 12, color: "#9b9b9b", flexShrink: 0 }}>
        {rank}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
          <div style={{ minWidth: 0, marginRight: 12 }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: "#111" }}>{domain}</span>
            {path && path !== "/" && (
              <span style={{ fontSize: 11, color: "#9b9b9b", marginLeft: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {path}
              </span>
            )}
          </div>
          <span style={{ fontSize: 12, color: "#6b6b6b", flexShrink: 0 }}>{count}</span>
        </div>
        <div style={{ height: 4, background: "#f0efec", borderRadius: 99, overflow: "hidden" }}>
          <div style={{
            height: "100%",
            width: `${pct}%`,
            background: color,
            opacity: 0.4 + 0.6 * (count / maxCount),
            borderRadius: 99,
            transition: "width 0.4s ease",
          }} />
        </div>
      </div>
    </div>
  );
}

const PAGE_SIZE = 5;

export function CitationList({ data, color, emptyMsg }) {
  const [visible, setVisible] = useState(PAGE_SIZE);

  useEffect(() => { setVisible(PAGE_SIZE); }, [data]);

  if (!data.length) return <p className="state-empty">{emptyMsg ?? "No data for this selection."}</p>;

  const maxCount = data[0]?.count ?? 1;
  const shown    = data.slice(0, visible);
  const hasMore  = visible < data.length;

  return (
    <div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {shown.map((c, i) => (
          <CitationRow key={c.url} rank={i + 1} url={c.url} count={c.count} maxCount={maxCount} color={color} />
        ))}
      </div>
      {hasMore && (
        <button
          onClick={() => setVisible(v => v + PAGE_SIZE)}
          style={{
            marginTop: 12,
            fontSize: 12,
            color: "#6b6b6b",
            background: "#f7f7f5",
            border: "0.5px solid rgba(0,0,0,0.12)",
            borderRadius: 6,
            padding: "5px 14px",
            cursor: "pointer",
            width: "100%",
          }}
        >
          Show {Math.min(PAGE_SIZE, data.length - visible)} more
          <span style={{ color: "#9b9b9b", marginLeft: 4 }}>({data.length - visible} remaining)</span>
        </button>
      )}
    </div>
  );
}

export function TabBar({ tabs, active, onChange }) {
  return (
    <div style={{ display: "flex", gap: 0, borderBottom: "0.5px solid rgba(0,0,0,0.10)", marginBottom: 20 }}>
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          style={{
            padding: "8px 16px",
            fontSize: 13,
            fontWeight: 500,
            color: active === tab.id ? "#378add" : "#6b6b6b",
            background: "none",
            border: "none",
            borderBottom: active === tab.id ? "2px solid #378add" : "2px solid transparent",
            cursor: "pointer",
            marginBottom: -1,
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function filterData(data, school) {
  const filtered = school === "All" ? data : data.filter(c => c.school === school);
  const sorted = [...filtered].sort((a, b) => b.count - a.count);
  return {
    qc:       sorted.filter(c => c.source_type === "QC owned"),
    external: sorted.filter(c => c.source_type === "external").slice(0, 20),
  };
}
