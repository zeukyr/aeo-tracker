export function TagList({ items, labelKey, countKey, color, bg }) {
  if (!items?.length) return <p className="state-empty">No data yet.</p>;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {items.map((item, i) => {
        const maxCount = items[0]?.[countKey] ?? 1;
        const opacity = 0.4 + 0.6 * (item[countKey] / maxCount);
        return (
          <span key={i} style={{
            background: bg,
            color,
            opacity,
            fontSize: 12,
            fontWeight: 500,
            padding: "5px 11px",
            borderRadius: 99,
            whiteSpace: "nowrap",
            cursor: "default",
          }}
            title={`${item[countKey]} mentions`}
          >
            {item[labelKey]}
          </span>
        );
      })}
    </div>
  );
}
