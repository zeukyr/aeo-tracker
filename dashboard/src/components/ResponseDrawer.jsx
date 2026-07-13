import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import { LLM_COLORS, LLM_LABELS } from "../lib/llm";

// ─── LLM response drawer (slide-in from right, with prev/next history nav) ───
export default function ResponseDrawer({ drawer, onClose }) {
  const { open, engine, promptText, promptId } = drawer;
  const { days } = useFilter();
  const [history, setHistory] = useState([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(false);

  // Fetch the full response history for this (prompt, engine) pair whenever the drawer opens
  useEffect(() => {
    if (!open || !promptId || !engine) return;
    setLoading(true);
    setIndex(0);
    const params = new URLSearchParams({ engine });
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/topic-prompt/${promptId}/responses?${params}`)
      .then(r => r.json())
      .then(rows => {
        setHistory(Array.isArray(rows) ? rows : []);
        setLoading(false);
      })
      .catch(() => {
        setHistory([]);
        setLoading(false);
      });
  }, [open, promptId, engine, days]);

  const total = history.length;
  const goPrevious = () => setIndex(i => Math.min(i + 1, total - 1));
  const goNext = () => setIndex(i => Math.max(i - 1, 0));

  useEffect(() => {
    if (!open) return;
    const handler = e => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") setIndex(i => Math.min(i + 1, total - 1));
      if (e.key === "ArrowRight") setIndex(i => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose, total]);

  if (!open) return null;
  const color = LLM_COLORS[engine] || "#888";
  const current = history[index];

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.18)", zIndex: 40 }} />
      <div style={{
        position: "fixed", top: 0, right: 0, bottom: 0,
        width: "min(520px, 90vw)",
        background: "#fff",
        borderLeft: "1px solid #e5e7eb",
        boxShadow: "-4px 0 24px rgba(0,0,0,0.08)",
        zIndex: 50,
        display: "flex", flexDirection: "column",
        overflow: "hidden",
      }}>
        {/* header */}
        <div style={{
          padding: "16px 20px",
          borderBottom: "1px solid #e5e7eb",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexShrink: 0,
        }}>
          <div>
            <p style={{ fontSize: 13, fontWeight: 600, color, marginBottom: 2 }}>
              {LLM_LABELS[engine] || engine}
            </p>
            <p style={{ fontSize: 11, color: "#9b9b9b" }}>
              {loading
                ? "Loading…"
                : total > 0
                  ? `Response ${index + 1} of ${total} · ${current?.date ?? ""}`
                  : "No responses"}
            </p>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "#9b9b9b", lineHeight: 1, padding: "4px 8px" }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* prompt context */}
        {promptText && (
          <div style={{ padding: "12px 20px", borderBottom: "1px solid #f0efec", flexShrink: 0 }}>
            <p style={{ fontSize: 11, color: "#9b9b9b", fontStyle: "italic" }}>"{promptText}"</p>
          </div>
        )}

        {/* prev / next navigation */}
        {total > 1 && (
          <div style={{
            padding: "8px 20px",
            borderBottom: "1px solid #f0efec",
            display: "flex", alignItems: "center", justifyContent: "space-between",
            flexShrink: 0,
          }}>
            <button
              onClick={goPrevious}
              disabled={index >= total - 1}
              style={{
                background: "none", border: "none", cursor: index >= total - 1 ? "default" : "pointer",
                fontSize: 12, color: index >= total - 1 ? "#d1d5db" : "#374151",
                display: "flex", alignItems: "center", gap: 4, padding: "4px 6px",
              }}
              aria-label="Previous response"
            >
              ← Previous
            </button>
            <button
              onClick={goNext}
              disabled={index <= 0}
              style={{
                background: "none", border: "none", cursor: index <= 0 ? "default" : "pointer",
                fontSize: 12, color: index <= 0 ? "#d1d5db" : "#374151",
                display: "flex", alignItems: "center", gap: 4, padding: "4px 6px",
              }}
              aria-label="Next response"
            >
              Next →
            </button>
          </div>
        )}

        {/* response body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
          {loading
            ? <p style={{ fontSize: 13, color: "#9b9b9b", fontStyle: "italic" }}>Loading…</p>
            : current?.response
              ? <p style={{ fontSize: 13, color: "#374151", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{current.response}</p>
              : <p style={{ fontSize: 13, color: "#9b9b9b", fontStyle: "italic" }}>No response available.</p>
          }
        </div>
      </div>
    </>
  );
}
