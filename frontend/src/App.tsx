import { useCallback, useState } from "react";
import "./App.css";
import { api, ApiError } from "./api/client";
import type { BuyerProfile, RecommendationResponse } from "./api/types";
import { storeSessionId, getStoredSessionId } from "./lib/session";
import { ChatScreen } from "./components/ChatScreen";
import { PreferenceReview } from "./components/PreferenceReview";
import { ResultsList } from "./components/ResultsList";
import { PropertyDetail } from "./components/PropertyDetail";
import { CompareView } from "./components/CompareView";
import { HandoffPanel } from "./components/HandoffPanel";
import { EvidencePanel } from "./components/EvidencePanel";
import { OrchestrationTrace } from "./components/OrchestrationTrace";

type Screen = "chat" | "preferences" | "results" | "detail" | "compare" | "handoff";

const STEPS: { key: Screen; label: string }[] = [
  { key: "chat", label: "1. Chat" },
  { key: "preferences", label: "2. Preferences" },
  { key: "results", label: "3. Results" },
  { key: "handoff", label: "4. Contact agent" },
];

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(getStoredSessionId());
  const [profile, setProfile] = useState<BuyerProfile | null>(null);
  const [screen, setScreen] = useState<Screen>("chat");

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
      setScreen("results");
    } catch (err) {
      setRecError(err instanceof ApiError ? err.message : "Could not fetch recommendations.");
    } finally {
      setRecLoading(false);
    }
  }, []);

  function handleExtracted(sid: string, extractedProfile: BuyerProfile) {
    setSessionId(sid);
    storeSessionId(sid);
    setProfile(extractedProfile);
    setScreen("preferences");
  }

  function handlePreferencesSaved(saved: BuyerProfile) {
    setProfile(saved);
    if (sessionId) fetchRecommendations(sessionId);
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
            <span key={s.key} className={screen === s.key ? "step active" : "step"}>
              {s.label}
            </span>
          ))}
        </nav>
      </header>

      <main className="app-main">
        {screen === "chat" && <ChatScreen sessionId={sessionId} onExtracted={handleExtracted} />}

        {screen === "preferences" && profile && sessionId && (
          <PreferenceReview sessionId={sessionId} profile={profile} onSaved={handlePreferencesSaved} />
        )}

        {recLoading && <section className="card">Loading recommendations…</section>}
        {recError && <section className="card error">{recError}</section>}

        {screen === "results" && recommendation && (
          <>
            <ResultsList
              result={recommendation}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
              onViewDetail={(id) => {
                setActiveListingId(id);
                setScreen("detail");
              }}
              onPreferPairwise={handlePreferPairwise}
              onLike={handleLike}
              onCompare={() => {
                setCompareIds(selectedIds);
                setScreen("compare");
              }}
            />
            <OrchestrationTrace trace={recommendation.trace} />
          </>
        )}

        {screen === "detail" && activeListingId && (
          <PropertyDetail
            listingId={activeListingId}
            onBack={() => setScreen("results")}
            onInterested={(id) => {
              setActiveListingId(id);
              setScreen("handoff");
            }}
          />
        )}

        {screen === "compare" && compareIds.length >= 2 && (
          <CompareView listingIds={compareIds} onBack={() => setScreen("results")} />
        )}

        {screen === "handoff" && activeListingId && (
          <HandoffPanel listingId={activeListingId} onBack={() => setScreen("results")} />
        )}
      </main>

      <EvidencePanel />
    </div>
  );
}
