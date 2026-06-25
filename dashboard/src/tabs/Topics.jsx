import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";

function visColor(score) {
  if (score >= 30) return "bg-green-100 text-green-700";
  if (score >= 10) return "bg-yellow-100 text-yellow-700";
  return "bg-red-100 text-red-700";
}

function VisBadge({ score }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded ${visColor(score)}`}>
      {score}%
    </span>
  );
}

function ProgressBar({ score }) {
  const color = score >= 30 ? "bg-green-400" : score >= 10 ? "bg-yellow-400" : "bg-red-400";
  return (
    <div className="w-24 h-2 bg-gray-100 rounded overflow-hidden">
      <div className={`h-full ${color}`} style={{ width: `${Math.min(score, 100)}%` }} />
    </div>
  );
}

const LLM_ENGINES = ["chatgpt", "gemini", "perplexity"];
const LLM_LABELS = { chatgpt: "ChatGPT", gemini: "Gemini", perplexity: "Perplexity" };

function RivalPills({ rivals }) {
  if (!rivals || rivals.length === 0) return <span className="text-gray-400 text-xs">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {rivals.map(r => (
        <span key={r} className="text-xs bg-gray-100 text-gray-600 rounded px-2 py-0.5">{r}</span>
      ))}
    </div>
  );
}

function PromptDetail({ prompt }) {
  const [fanoutsOpen, setFanoutsOpen] = useState(false);

  return (
    <tr>
      <td colSpan={6} className="px-4 pb-4 pt-1">
        <div className="ml-8 bg-gray-50 rounded-lg p-4 space-y-4">

          {/* Full prompt text */}
          <p className="italic text-gray-600 text-sm">"{prompt.text}"</p>

          {/* LLM Breakdown */}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase mb-2">LLM Breakdown</p>
            <div className="space-y-2">
              {LLM_ENGINES.map(engine => {
                const r = prompt.results.find(x => x.llm === engine);
                if (!r) return null;
                return (
                  <div key={engine} className="flex items-center gap-4">
                    <span className="text-xs font-medium w-20 text-gray-700">{LLM_LABELS[engine]}</span>
                    <span className="text-xs text-gray-500">RES {r.responseRate}%</span>
                    <span className="text-gray-300 text-xs">·</span>
                    <span className="text-xs text-gray-500">CIT {r.citationRate}%</span>
                    <ProgressBar score={r.visibility} />
                    <VisBadge score={r.visibility} />
                  </div>
                );
              })}
            </div>
          </div>

          {/* Competitors */}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase mb-2">Competitors Mentioned</p>
            {prompt.results.flatMap(r => r.competitorsMentioned).length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {[...new Set(prompt.results.flatMap(r => r.competitorsMentioned))].map(c => (
                  <span key={c} className="text-xs bg-gray-100 text-gray-700 rounded px-2 py-0.5">{c}</span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-400">No competitors mentioned</p>
            )}
          </div>

          {/* Query Fanouts */}
          <div>
            <button
              onClick={() => setFanoutsOpen(o => !o)}
              className="text-xs font-medium text-gray-500 uppercase flex items-center gap-1"
            >
              <span>{fanoutsOpen ? "▼" : "▶"}</span> Query Fanouts
            </button>
            {fanoutsOpen && (
              <p className="text-xs text-gray-400 mt-2 ml-4">No fanout data available yet</p>
            )}
          </div>

          {/* Metadata */}
          <div className="flex gap-6 text-xs text-gray-400 border-t border-gray-200 pt-3">
            <span>Buyer Profile: —</span>
            <span>Location: Global</span>
            <span>Tags: —</span>
          </div>
        </div>
      </td>
    </tr>
  );
}

function PromptRow({ prompt, expanded, onToggle }) {
  return (
    <>
      <tr
        className="border-t border-gray-100 hover:bg-gray-50 cursor-pointer"
        onClick={onToggle}
      >
        <td className="px-4 py-3 pl-10">
          <div className="flex items-center gap-2">
            <span className="text-gray-400 text-xs">{expanded ? "▼" : "▶"}</span>
            <span className="text-sm text-gray-700 truncate max-w-xs" title={prompt.text}>
              "{prompt.text}"
            </span>
          </div>
        </td>
        <td className="px-3 py-3"><VisBadge score={prompt.visibility} /></td>
        {LLM_ENGINES.map(engine => (
          <td key={engine} className="px-3 py-3">
            {prompt.llms[engine] != null
              ? <VisBadge score={prompt.llms[engine]} />
              : <span className="text-gray-300 text-xs">—</span>}
          </td>
        ))}
        <td className="px-3 py-3"><RivalPills rivals={prompt.topRivals} /></td>
      </tr>
      {expanded && <PromptDetail prompt={prompt} />}
    </>
  );
}

function TopicRow({ topic, expanded, onToggle, expandedPrompts, onTogglePrompt }) {
  return (
    <>
      <tr
        className="bg-gray-50 cursor-pointer hover:bg-gray-100 border-t border-gray-200"
        onClick={onToggle}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-gray-500 text-xs">{expanded ? "▼" : "▶"}</span>
            <div>
              <p className="text-sm font-medium text-gray-800">{topic.name}</p>
              <p className="text-xs text-gray-400">{topic.promptCount} prompts</p>
            </div>
          </div>
        </td>
        <td className="px-3 py-3"><VisBadge score={topic.visibility} /></td>
        {LLM_ENGINES.map(engine => (
          <td key={engine} className="px-3 py-3">
            {topic.llms[engine] != null
              ? <VisBadge score={topic.llms[engine]} />
              : <span className="text-gray-300 text-xs">—</span>}
          </td>
        ))}
        <td className="px-3 py-3"><RivalPills rivals={topic.topRivals} /></td>
      </tr>
      {expanded && topic.prompts.map(prompt => (
        <PromptRow
          key={prompt.id}
          prompt={prompt}
          expanded={expandedPrompts.has(prompt.id)}
          onToggle={e => { e.stopPropagation(); onTogglePrompt(prompt.id); }}
        />
      ))}
    </>
  );
}

export default function Topics() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedTopics, setExpandedTopics] = useState(new Set());
  const [expandedPrompts, setExpandedPrompts] = useState(new Set());

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/topics`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, []);

  function toggleTopic(name) {
    setExpandedTopics(prev => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  function togglePrompt(id) {
    setExpandedPrompts(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <table className="w-full text-left table-fixed">
        <colgroup>
          <col className="w-[35%]" />
          <col className="w-[10%]" />
          <col className="w-[10%]" />
          <col className="w-[10%]" />
          <col className="w-[10%]" />
          <col className="w-[25%]" />
        </colgroup>
        <thead>
          <tr className="border-b border-gray-200">
            <th className="px-4 py-2 text-xs text-gray-500 uppercase font-medium">Prompt / Topic</th>
            <th className="px-3 py-2 text-xs text-gray-500 uppercase font-medium">Visibility</th>
            <th colSpan={3} className="px-3 py-2 text-xs text-gray-500 uppercase font-medium text-center border-l border-gray-100">
              LLMs
            </th>
            <th className="px-3 py-2 text-xs text-gray-500 uppercase font-medium">Top Rivals</th>
          </tr>
          <tr className="border-b border-gray-100 bg-gray-50">
            <th />
            <th />
            {LLM_ENGINES.map(engine => (
              <th key={engine} className="px-3 py-1.5 text-xs text-gray-400 font-medium border-l border-gray-100">
                {LLM_LABELS[engine]}
              </th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          {data.map(topic => (
            <TopicRow
              key={topic.name}
              topic={topic}
              expanded={expandedTopics.has(topic.name)}
              onToggle={() => toggleTopic(topic.name)}
              expandedPrompts={expandedPrompts}
              onTogglePrompt={togglePrompt}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}