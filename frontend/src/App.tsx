import { useCallback, useState } from "react";
import "./App.css";
import { api, ApiError } from "./api/client";
import type { BuyerProfile, RecommendationResponse } from "./api/types";
import { storeSessionId, getStoredSessionId } from "./lib/session";
import { ModeSelect } from "./components/ModeSelect";
import { VoiceChat } from "./components/VoiceChat";
import { QuestionFlow } from "./components/QuestionFlow";
import { ResultsList } from "./components/ResultsList";
import { PropertyDetail } from "./components/PropertyDetail";
import { CompareView } from "./components/CompareView";
import { HandoffPanel } from "./components/HandoffPanel";
import { EvidencePanel } from "./components/EvidencePanel";
import { OrchestrationTrace } from "./components/OrchestrationTrace";

type Screen = "mode" | "voice" | "questions" | "preferences" | "results" | "detail" | "compare" | "handoff";

const STEPS: { key: Screen; label: string }[] = [
  { key: "mode", label: "1. Chat" },
  { key: "questions", label: "2. Preferences" },
  { key: "results", label: "3. Results" },
  { key: "handoff", label: "4. Contact agent" },
];

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(getStoredSessionId());
  const [nav, setNav] = useState<{ screen: Screen; history: Screen[] }>({ screen: "mode", history: [] });
  const screen = nav.screen;

  /** Move forward, remembering where we came from so Back returns to the true previous page. */
  const navigate = useCallback((next: Screen) => {
    setNav((n) => (n.screen === next ? n : { screen: next, history: [...n.history, n.screen] }));
  }, []);

  const goBack = useCallback(() => {
    setNav((n) =>
      n.history.length === 0 ? n : { screen: n.history[n.history.length - 1], history: n.history.slice(0, -1) },
    );
  }, []);

  const [recommendation, setRecommendation] = useState<RecommendationResponse | null>(null);
  const [recLoading, setRecLoading] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [activeListingId, setActiveListingId] = useState<string | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);

  const fetchRecommendations = useCallback(async (sid: string) => {
    setRecLoading(true);
    setRecError(null);
    try {
      const res = await api.getRecommendations(sid, 5);
      setRecommendation(res);
      navigate("results");
    } catch (err) {
      setRecError(err instanceof ApiError ? err.message : "Could not fetch recommendations.");
    } finally {
      setRecLoading(false);
    }
  }, [navigate]);

  /** Voice replaces the typed questions: drop it from history so Back from results doesn't restart the call. */
  function handleVoiceComplete(sid: string, saved: BuyerProfile) {
    goBack();
    handleQuestionsComplete(sid, saved);
  }

  function handleQuestionsComplete(sid: string, _saved: BuyerProfile) {
    setSessionId(sid);
    storeSessionId(sid);
    fetchRecommendations(sid);
  }

  async function handleLike(listingId: string) {
    if (!sessionId) return;
    const res = await api.sendFeedback(sessionId, listingId, null);
    setRecommendation((prev) =>
      prev
        ? { ...prev, run_id: res.new_run_id, items: res.items, returned_count: res.items.length, trace: res.trace }
        : prev,
    );
  }

  async function handlePreferPairwise(chosenId: string, rejectedId: string) {
    if (!sessionId) return;
    const res = await api.sendFeedback(sessionId, chosenId, rejectedId);
    setRecommendation((prev) =>
      prev
        ? { ...prev, run_id: res.new_run_id, items: res.items, returned_count: res.items.length, trace: res.trace }
        : prev,
    );
    setSelectedIds([]);
  }

  function toggleSelect(listingId: string) {
    setSelectedIds((prev) => {
      if (prev.includes(listingId)) return prev.filter((id) => id !== listingId);
      if (prev.length >= 3) return prev;
      return [...prev, listingId];
    });
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>🏠 Homerun</h1>
        <nav className="steps">
          {STEPS.map((s) => (
            <span key={s.key} className={(screen === "voice" ? "questions" : screen) === s.key ? "step active" : "step"}>
              {s.label}
            </span>
          ))}
        </nav>
      </header>

      <main className="app-main">
        {screen === "mode" && <ModeSelect onVoice={() => navigate("voice")} onType={() => navigate("questions")} />}

        {screen === "voice" && (
          <VoiceChat
            onComplete={handleVoiceComplete}
            onBack={goBack}
            onTypeInstead={() => {
              goBack();
              navigate("questions");
            }}
          />
        )}

        {/* Kept mounted (hidden) so answers survive going Back from results to change them. */}
        <div hidden={screen !== "questions"}>
          <QuestionFlow onComplete={handleQuestionsComplete} onBack={goBack} />
        </div>

        {recLoading && <section className="card">Loading recommendations…</section>}
        {recError && <section className="card error">{recError}</section>}

        {screen === "results" && recommendation && (
          <>
            <button className="ghost back-btn" onClick={goBack}>
              ← Back
            </button>
            <ResultsList
              result={recommendation}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
              onViewDetail={(id) => {
                setActiveListingId(id);
                navigate("detail");
              }}
              onPreferPairwise={handlePreferPairwise}
              onLike={handleLike}
              onCompare={() => {
                setCompareIds(selectedIds);
                navigate("compare");
              }}
            />
            <OrchestrationTrace trace={recommendation.trace} />
          </>
        )}

        {screen === "detail" && activeListingId && (
          <PropertyDetail
            listingId={activeListingId}
            onBack={goBack}
            onInterested={(id) => {
              setActiveListingId(id);
              navigate("handoff");
            }}
          />
        )}

        {screen === "compare" && compareIds.length >= 2 && (
          <CompareView listingIds={compareIds} onBack={goBack} />
        )}

        {screen === "handoff" && activeListingId && (
          <HandoffPanel listingId={activeListingId} onBack={goBack} />
        )}
      </main>

      <EvidencePanel />
    </div>
  );
}
