import { useState } from "react";
import Overview from "./tabs/Overview";
import Visibility from "./tabs/Visibility";
import Sentiment from "./tabs/Sentiment";
import Competitors from "./tabs/Competitors";
import Citations from "./tabs/Citations";
import Explorer from "./tabs/Explorer";
import { useFilter } from "./context/useFilter";
import { PERIOD_OPTIONS } from "./context/FilterContextConstants";
import Topics from "./tabs/Topics";
import Recommendations from "./tabs/Recommendations";

const TABS = ["Overview", "Visibility", "Sentiment", "Competitors", "Citations", "Explorer", "Topics", "Recommendations"];

function App() {
  const [activeTab, setActiveTab] = useState("Overview");
  const { days, setDays } = useFilter();

  return (
    <div className="max-w-6xl mx-auto py-8 px-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-medium">QC AI Visibility Dashboard</h1>
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
      {activeTab === "Explorer" && <Explorer />}
      {activeTab === "Topics" && <Topics />}
      {activeTab === "Recommendations" && <Recommendations />}
    </div>
  );
}

export default App;