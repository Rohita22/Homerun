/**
 * Session identity lives client-side as a plain string (no cookies — see backend README
 * "Connecting a frontend"). Persisted in localStorage purely as a per-browser convenience so a
 * page refresh doesn't lose the buyer's place; it is never relied on for anything the server
 * must trust (the backend re-validates everything server-side on every call).
 */

const STORAGE_KEY = "homerun.session_id";

export function getStoredSessionId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeSessionId(sessionId: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, sessionId);
  } catch {
    // Private browsing / blocked storage — the app still works for this page lifetime.
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
