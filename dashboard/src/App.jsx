import { useState } from "react";
import Overview from "./tabs/Overview";
import Visibility from "./tabs/Visibility";
import Sentiment from "./tabs/Sentiment";
import Competitors from "./tabs/Competitors";

const TABS = ["Overview", "Visibility", "Sentiment", "Competitors", "Citations", "Explorer"];

function App() {
  const [activeTab, setActiveTab] = useState("Overview");

  return (
    <div className="max-w-6xl mx-auto py-8 px-4">
      <h1 className="text-xl font-medium mb-6">QC AI Visibility Dashboard</h1>

      <div className="flex gap-1 border-b border-gray-200 mb-6 overflow-x-auto">
        {TABS.map((tab) => (
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
      {/* {activeTab === "Citations" && <Citations />}
      {activeTab === "Explorer" && <Explorer />} */}
    </div>
  );
}

export default App;