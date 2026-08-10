import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";

// Site-wide, LLM-free structural/schema audit of QC's own pages - the cheap
// counterpart to the per-question fix-branch scorecard in Recommendations.
// No cooldown/generation-status gate here (unlike the LLM-metered engines):
// this computes on demand from the already-cached page_facts data, so a
// re-run just re-fetches whatever's stale, not a rate-limited resource.

const SEVERITY_LABEL = { high: "Critical", medium: "Medium" };
const SEVERITY_COLOR = {
  high:   { bg: "#fcebeb", text: "#a32d2d" },
  medium: { bg: "#fbf0de", text: "#ba7517" },
};

function SeverityPill({ weight }) {
  const c = SEVERITY_COLOR[weight] || { bg: "#f0efec", text: "#5f5e5a" };
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: "2px 9px", borderRadius: 99,
      background: c.bg, color: c.text, whiteSpace: "nowrap",
    }}>
      {SEVERITY_LABEL[weight] || weight}
    </span>
  );
}

function IssuesSummary({ issues }) {
  const [expandedId, setExpandedId] = useState(null);
  const critical = issues.filter(r => r.geo_weight === "high").length;
  const medium = issues.filter(r => r.geo_weight === "medium").length;

  if (!issues.length) {
    return <p className="state-empty">No structural or schema issues found across the analyzed pages.</p>;
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 12, marginBottom: 14 }}>
        <div style={{ flex: 1, background: "#fcebeb", borderRadius: 10, padding: "10px 14px" }}>
          <p style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "#a32d2d", margin: 0 }}>Critical</p>
          <p style={{ fontSize: 22, fontWeight: 600, color: "#a32d2d", margin: 0 }}>{critical}</p>
        </div>
        <div style={{ flex: 1, background: "#fbf0de", borderRadius: 10, padding: "10px 14px" }}>
          <p style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "#ba7517", margin: 0 }}>Medium</p>
          <p style={{ fontSize: 22, fontWeight: 600, color: "#ba7517", margin: 0 }}>{medium}</p>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {issues.map(row => (
          <div key={row.feature_id} style={{ border: "0.5px solid rgba(0,0,0,0.10)", borderRadius: 8 }}>
            <button
              type="button"
              onClick={() => setExpandedId(expandedId === row.feature_id ? null : row.feature_id)}
              style={{
                width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
                gap: 10, padding: "9px 12px", background: "none", border: "none", cursor: "pointer",
                fontFamily: "inherit", textAlign: "left",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 11, color: "#9b9b9b" }}>{expandedId === row.feature_id ? "▾" : "▸"}</span>
                <span style={{ fontSize: 13, color: "#111", fontWeight: 500 }}>{row.label}</span>
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <SeverityPill weight={row.geo_weight} />
                <span style={{ fontSize: 12, color: "#6b6b6b", fontVariantNumeric: "tabular-nums" }}>
                  {row.page_count} page{row.page_count === 1 ? "" : "s"}
                </span>
              </span>
            </button>
            {expandedId === row.feature_id && (
              <div style={{ padding: "0 12px 10px 32px", display: "flex", flexDirection: "column", gap: 4 }}>
                {row.pages.map(url => (
                  <a key={url} href={url} target="_blank" rel="noreferrer"
                     style={{ fontFamily: "ui-monospace, monospace", fontSize: 11.5, color: "#378add" }}>
                    {url}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function HygieneSummary({ hygiene }) {
  const [open, setOpen] = useState(false);
  if (!hygiene.length) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontFamily: "inherit", fontSize: 12, color: "#6b6b6b", borderBottom: "1px dashed rgba(0,0,0,0.20)" }}
      >
        {open ? "Hide" : "Show"} {hygiene.length} hygiene item{hygiene.length === 1 ? "" : "s"} (low citation impact) ▾
      </button>
      {open && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
          <p style={{ fontSize: 11.5, color: "#9b9b9b", maxWidth: "48ch", margin: 0 }}>
            Our own citation-correlation data rates these as near-zero independent effect on AI
            citation - hygiene, not a lever worth prioritizing.
          </p>
          {hygiene.map(row => (
            <div key={row.feature_id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#6b6b6b" }}>
              <span>{row.label}</span>
              <span style={{ fontVariantNumeric: "tabular-nums" }}>{row.page_count} page{row.page_count === 1 ? "" : "s"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PageTable({ pages, showSchool }) {
  const ranked = [...pages].sort((a, b) => (b.critical_count - a.critical_count) || (b.medium_count - a.medium_count));
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            <th style={thStyle}>Page</th>
            {showSchool && <th style={thStyle}>School</th>}
            <th style={thStyle}>Status</th>
            <th style={thStyle}>Critical</th>
            <th style={thStyle}>Medium</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map(p => (
            <tr key={p.url}>
              <td style={tdStyle}>
                <a href={p.url} target="_blank" rel="noreferrer" style={{ fontFamily: "ui-monospace, monospace", fontSize: 11.5, color: "#111" }}>
                  {p.url.replace(/^https?:\/\//, "")}
                </a>
              </td>
              {showSchool && <td style={tdStyle}>{p.school || "General"}</td>}
              <td style={tdStyle}>
                {p.status === "ok"
                  ? <span style={{ color: "#3b6d11" }}>readable</span>
                  : <span style={{ color: "#9b9b9b" }}>{p.status || "unreadable"}</span>}
              </td>
              <td style={{ ...tdStyle, fontVariantNumeric: "tabular-nums" }}>
                {p.status === "ok" ? (p.critical_count > 0 ? <b style={{ color: "#a32d2d" }}>{p.critical_count}</b> : 0) : "—"}
              </td>
              <td style={{ ...tdStyle, fontVariantNumeric: "tabular-nums" }}>
                {p.status === "ok" ? (p.medium_count > 0 ? <b style={{ color: "#ba7517" }}>{p.medium_count}</b> : 0) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const thStyle = {
  textAlign: "left", fontSize: 9.5, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase",
  color: "#9b9b9b", padding: "0 8px 6px 0", borderBottom: "0.5px solid rgba(0,0,0,0.10)",
};
const tdStyle = { padding: "7px 8px 7px 0", borderBottom: "0.5px solid rgba(0,0,0,0.10)", verticalAlign: "middle" };

export default function SiteAudit() {
  const { school } = useFilter();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // No synchronous setState here - loading/refreshing are set by their call
  // sites (the effect relies on `loading`'s initial useState value; the
  // refresh button sets `refreshing` itself before calling this) so the
  // effect body itself never calls setState synchronously.
  const load = (refresh = false) => {
    const params = new URLSearchParams();
    if (school && school !== "All") params.append("school", school);
    if (refresh) params.append("refresh", "true");
    fetch(`${API_BASE_URL}/api/site-audit?${params}`)
      .then(r => {
        if (!r.ok) throw new Error(`Server error ${r.status}`);
        return r.json();
      })
      .then(data => {
        setResult(data);
        setError(null);
        setLoading(false);
        setRefreshing(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
        setRefreshing(false);
      });
  };

  useEffect(() => load(false), [school]);

  if (loading) return <p className="state-msg">Loading…</p>;
  if (error) return <p className="state-msg state-msg--error">Error: {error}</p>;
  if (!result || result.urls_total === 0) {
    return (
      <p className="state-empty">
        No QC sitemap pages cached yet - run the sitemap refresh, then reload this tab.
      </p>
    );
  }

  const showSchool = !school || school === "All";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="card">
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <p className="panel-title">Site Audit</p>
            <p className="panel-subtitle" style={{ marginBottom: 0 }}>
              {result.urls_readable}/{result.urls_total} QC pages readable
              {showSchool ? "" : ` · ${school}`} — structural &amp; schema checks only, no
              competitor comparison, no LLM calls.
            </p>
          </div>
          <button
            className="btn btn--ghost"
            onClick={() => { setRefreshing(true); load(true); }}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing…" : "↻ Re-run audit"}
          </button>
        </div>
      </div>

      <div className="card">
        <p className="panel-title">Outstanding issues</p>
        <p className="panel-subtitle">Missing schema, thin structure, or out-of-range metrics vs. GEO citation-research targets — QC's own pages only, not benchmarked against any specific competitor.</p>
        <IssuesSummary issues={result.issues_summary} />
        <HygieneSummary hygiene={result.hygiene_summary} />
      </div>

      <div className="card">
        <p className="panel-title">Page-by-page</p>
        <p className="panel-subtitle">{result.pages.length} page{result.pages.length === 1 ? "" : "s"}, worst first.</p>
        <PageTable pages={result.pages} showSchool={showSchool} />
      </div>
    </div>
  );
}
