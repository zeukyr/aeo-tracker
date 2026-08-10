import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import Overview from "./tabs/Overview";
import Visibility from "./tabs/Visibility";
import Sentiment from "./tabs/Sentiment";
import Competitors from "./tabs/Competitors";
import Citations from "./tabs/Citations";
import Prompts from "./tabs/Prompts";
import Recommendations from "./tabs/Recommendations";
import BlogIdeas from "./tabs/BlogIdeas";
import BlogIdeaDetail from "./pages/BlogIdeaDetail";
import BlogPersonas from "./pages/BlogPersonas";
import QuestionDetail from "./pages/QuestionDetail";
import QuestionPlan from "./pages/QuestionPlan";
import RecommendationDetail from "./pages/RecommendationDetail";
import { useFilter } from "./context/useFilter";
import { PERIOD_OPTIONS, SCHOOL_OPTIONS } from "./context/FilterContextConstants";

// Each tab is a real route; detail pages get their own URLs underneath
// (/prompts/:promptId, /recommendations/:recId) so they can be shared,
// bookmarked, and navigated with the browser's back button.
const TABS = [
  { label: "Overview", path: "/overview" },
  { label: "Visibility", path: "/visibility" },
  { label: "Sentiment", path: "/sentiment" },
  { label: "Competitors", path: "/competitors" },
  { label: "Citations", path: "/citations" },
  { label: "Prompts", path: "/prompts" },
  { label: "Recommendations", path: "/recommendations" },
  { label: "Blog Ideas", path: "/blog-ideas" },
];

function App() {
  const { days, setDays, school, setSchool } = useFilter();

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
          <NavLink
            key={tab.path}
            to={tab.path}
            className={({ isActive }) =>
              `px-4 py-2 text-sm whitespace-nowrap ${
                isActive
                  ? "text-blue-600 border-b-2 border-blue-600 font-medium"
                  : "text-gray-500"
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </div>

      <Routes>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<Overview />} />
        <Route path="/visibility" element={<Visibility />} />
        <Route path="/sentiment" element={<Sentiment />} />
        <Route path="/competitors" element={<Competitors />} />
        <Route path="/citations" element={<Citations />} />
        <Route path="/prompts" element={<Prompts />} />
        <Route path="/prompts/:promptId" element={<QuestionDetail />} />
        <Route path="/prompts/:promptId/plan" element={<QuestionPlan />} />
        <Route path="/recommendations" element={<Recommendations />} />
        <Route path="/recommendations/:recId" element={<RecommendationDetail />} />
        <Route path="/blog-ideas" element={<BlogIdeas />} />
        <Route path="/blog-ideas/personas" element={<BlogPersonas />} />
        <Route path="/blog-ideas/:ideaId" element={<BlogIdeaDetail />} />
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Routes>
    </div>
  );
}

export default App;
