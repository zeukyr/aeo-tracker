import { useState } from "react";
import Overview from "./tabs/Overview";
import Visibility from "./tabs/Visibility";
import Sentiment from "./tabs/Sentiment";
import Competitors from "./tabs/Competitors";
import Citations from "./tabs/Citations";
import { useFilter } from "./context/useFilter";
import { PERIOD_OPTIONS, SCHOOL_OPTIONS } from "./context/FilterContextConstants";
import Prompts from "./tabs/Prompts";
import Recommendations from "./tabs/Recommendations";

const TABS = ["Overview", "Visibility", "Sentiment", "Competitors", "Citations", "Prompts", "Recommendations"];

function App() {
  const [activeTab, setActiveTab] = useState("Overview");
  const [focusedPromptId, setFocusedPromptId] = useState(null);
  const [focusedRecId, setFocusedRecId] = useState(null);
  const { days, setDays, school, setSchool } = useFilter();

  const openPrompt = (promptId) => {
    setFocusedPromptId(promptId);
    setActiveTab("Prompts");
  };

  const closePrompt = () => setFocusedPromptId(null);

  const openRecommendation = (recId) => {
    setFocusedRecId(recId);
    setActiveTab("Recommendations");
  };

  const closeRecommendation = () => setFocusedRecId(null);

  return (
    <div className="max-w-6xl mx-auto py-8 px-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-medium">QC AI Visibility Dashboard</h1>
        <div className="flex items-center gap-2">
          <select
            className="text-sm border border-gray-200 rounded px-3 py-1.5"
            value={school}
            onChange={e => setSchool(e.target.value)}
          >
            {SCHOOL_OPTIONS.map(s => (
              <option key={s} value={s}>{s === "All" ? "All schools" : s}</option>
            ))}
          </select>
          <select
            className="text-sm border border-gray-200 rounded px-3 py-1.5"
            value={days ?? ""}
            onChange={e => setDays(e.target.value ? parseInt(e.target.value) : null)}
          >
            {PERIOD_OPTIONS.map(o => (
              <option key={o.label} value={o.value ?? ""}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex gap-1 border-b border-gray-200 mb-6 overflow-x-auto">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm whitespace-nowrap ${
              activeTab === tab
                ? "text-blue-600 border-b-2 border-blue-600 font-medium"
                : "text-gray-500"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "Overview" && <Overview />}
      {activeTab === "Visibility" && <Visibility />}
      {activeTab === "Sentiment" && <Sentiment />}
      {activeTab === "Competitors" && <Competitors />}
      {activeTab === "Citations" && <Citations />}
      {activeTab === "Prompts" && (
        <Prompts
          focusedPromptId={focusedPromptId}
          onOpenPrompt={openPrompt}
          onClosePrompt={closePrompt}
          onOpenRecommendation={openRecommendation}
        />
      )}
      {activeTab === "Recommendations" && (
        <Recommendations
          onOpenPrompt={openPrompt}
          focusedRecId={focusedRecId}
          onCloseRecommendation={closeRecommendation}
        />
      )}
    </div>
  );
}

export default App;