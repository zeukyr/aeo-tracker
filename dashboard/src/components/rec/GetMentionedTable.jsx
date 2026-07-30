import { useMemo, useState } from "react";
import { bucketLabel, channelLabel, feasibilityOf, STATUS_LABELS } from "../../lib/recview";

// Flat, sortable/filterable table for "Get mentioned in third parties" -
// replaces the per-question card groups. A queue of directory/roundup/
// review opportunities is something a person scans and triages in bulk
// (which ones are open-channel and worth doing today?), not something that
// benefits from one big card each - inline card expansion pushed the whole
// list around and made scrolling past more than a few of them painful.
// Clicking a row goes straight to the existing /recommendations/:id detail
// page rather than expanding in place.

const PRIORITY_ORDER = { high: 0, medium: 1, low: 2 };
const CHANNEL_ORDER = { open: 0, gated: 1, closed: 2, unknown: 3 };

// "Type" isn't a field on the rec - it's read off the same signals the card
// verdict line uses: inclusion opportunities split on whether the listing
// page is a directory or a roundup (mirrors _inclusion_recs' is_directory
// ternary server-side); a reach_out branch's own primary rec's target IS
// the question's dominant bucket, so dominant_source describes it correctly
// (review/reference/certifying_body/editorial). A reach_out_fanout
// companion is different: dominant_source there is the PARENT question's
// overall bucket, not this specific companion's own target - fanout
// deliberately surfaces non-dominant-bucket winners too (question_router.py
// _reach_out_fanout), so trusting dominant_source there mislabeled a
// coursera.org review-bucket companion as "competitor" during UI testing.
// action_type (community vs not) is the only per-target signal available
// client-side for fan-out rows without a backend change.
function typeOf(rec) {
  const branch = rec.detail?.router?.branch;
  if (branch === "inclusion_opportunity") {
    return rec.action_type === "citation" ? "Directory" : "Roundup";
  }
  if (branch === "reach_out_fanout") {
    return rec.action_type === "community" ? "Community" : "Third party";
  }
  const bucket = rec.detail?.router?.dominant_source;
  if (bucket) return bucketLabel(bucket);
  if (rec.action_type === "community") return "Community";
  return "Third party";
}

const SORTERS = {
  target: (r) => channelLabel(r.target).toLowerCase(),
  type: (r) => typeOf(r).toLowerCase(),
  priority: (r) => PRIORITY_ORDER[r.priority] ?? 3,
  channel: (r) => CHANNEL_ORDER[feasibilityOf(r)?.feasibility] ?? 4,
};

function SortHeader({ id, label, sort, onSort }) {
  const active = sort.column === id;
  return (
    <th
      className={`gm-table__th gm-table__th--sortable${active ? " gm-table__th--active" : ""}`}
      onClick={() => onSort(id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSort(id); } }}
    >
      {label}{active ? (sort.dir === "asc" ? " ▲" : " ▼") : ""}
    </th>
  );
}

export default function GetMentionedTable({ recs, onOpenDetail }) {
  const [sort, setSort] = useState({ column: "priority", dir: "asc" });
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [channelFilter, setChannelFilter] = useState("all");

  const handleSort = (column) => {
    setSort((prev) =>
      prev.column === column ? { column, dir: prev.dir === "asc" ? "desc" : "asc" } : { column, dir: "asc" });
  };

  const filtered = useMemo(() => recs.filter((r) => {
    if (priorityFilter !== "all" && r.priority !== priorityFilter) return false;
    if (channelFilter !== "all" && feasibilityOf(r)?.feasibility !== channelFilter) return false;
    return true;
  }), [recs, priorityFilter, channelFilter]);

  const sorted = useMemo(() => {
    const key = SORTERS[sort.column] ?? SORTERS.priority;
    const rows = [...filtered].sort((a, b) => {
      const av = key(a);
      const bv = key(b);
      if (av < bv) return -1;
      if (av > bv) return 1;
      return 0;
    });
    if (sort.dir === "desc") rows.reverse();
    return rows;
  }, [filtered, sort]);

  if (recs.length === 0) return null;

  return (
    <div className="gm-table-wrap">
      <div className="gm-table__filters">
        <select className="select-sm" value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
          <option value="all">All priorities</option>
          <option value="high">High priority</option>
          <option value="medium">Medium priority</option>
          <option value="low">Low priority</option>
        </select>
        <select className="select-sm" value={channelFilter} onChange={(e) => setChannelFilter(e.target.value)}>
          <option value="all">All channels</option>
          <option value="open">Open — self-serve</option>
          <option value="gated">Gated — approval</option>
        </select>
        <span className="gm-table__count">{sorted.length} of {recs.length}</span>
      </div>
      <div className="gm-table__scroll">
        <table className="gm-table">
          <thead>
            <tr>
              <SortHeader id="target" label="Target" sort={sort} onSort={handleSort} />
              <SortHeader id="type" label="Type" sort={sort} onSort={handleSort} />
              <th className="gm-table__th">Problem</th>
              <SortHeader id="priority" label="Priority" sort={sort} onSort={handleSort} />
              <SortHeader id="channel" label="Channel" sort={sort} onSort={handleSort} />
              <th className="gm-table__th" aria-label="Open" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((rec) => {
              const feas = feasibilityOf(rec);
              const statusLabel = STATUS_LABELS[rec.status];
              return (
                <tr
                  key={rec.id}
                  className="gm-table__row"
                  onClick={() => onOpenDetail(rec.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === "Enter") onOpenDetail(rec.id); }}
                >
                  <td className="gm-table__td gm-table__td--target">
                    <a href={rec.target} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                      {channelLabel(rec.target)}
                    </a>
                  </td>
                  <td className="gm-table__td">{typeOf(rec)}</td>
                  <td className="gm-table__td gm-table__td--problem" title={rec.problem}>
                    {statusLabel && <span className="chip gm-table__status">{statusLabel}</span>}
                    {rec.problem}
                  </td>
                  <td className="gm-table__td">
                    <span className={`priority-pill priority-pill--${rec.priority}`}>{rec.priority}</span>
                  </td>
                  <td className="gm-table__td">
                    {feas?.feasibility && (
                      <span
                        className={`chip ${feas.feasibility === "gated" ? "chip--gated" : "chip--open"}`}
                        title={feas.mechanism || feas.evidence}
                      >
                        {feas.feasibility === "gated" ? "gated" : feas.feasibility === "open" ? "open" : feas.feasibility}
                      </span>
                    )}
                  </td>
                  <td className="gm-table__td gm-table__td--arrow">→</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
