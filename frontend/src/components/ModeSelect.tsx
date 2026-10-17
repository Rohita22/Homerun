interface Props {
  onVoice: () => void;
  onType: () => void;
}

export function ModeSelect({ onVoice, onType }: Props) {
  return (
    <section className="card">
      <h2>How would you like to tell us what you want?</h2>
      <p className="muted">Pick one to get started.</p>
      <div className="choice-grid">
        <button className="choice-card" onClick={onVoice}>
          <span className="choice-icon">🎙️</span>
          <span className="choice-title">Voice AI</span>
          <span className="choice-sub">Just talk — Ava does the rest</span>
        </button>
        <button className="choice-card" onClick={onType}>
          <span className="choice-icon">⌨️</span>
          <span className="choice-title">Type it myself</span>
          <span className="choice-sub">Answer a few quick questions</span>
        </button>
      </div>
    </section>
  );
}
