"""Voice assistant session: bridges one browser WebSocket to one Gemini Live API session.

Browser -> backend: binary frames = 16 kHz mono PCM16 microphone audio; JSON text frames = control.
Backend -> browser: binary frames = 24 kHz mono PCM16 assistant audio; JSON text frames = events
(``transcript``, ``state``, ``interrupted``, ``turn_complete``, ``complete``, ``error``).

The backend owns the model configuration, system prompt and the ``save_preferences`` tool, so the
Gemini API key never reaches the browser. Audio is relayed without buffering to keep latency at
the model's own time-to-first-audio.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.voice_preferences import PROPERTY_TYPES, QUESTION_LABELS, TOWNS, VoicePreferences

logger = get_logger(__name__)

GEMINI_LIVE_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)

SYSTEM_PROMPT = f"""You are Ava, a warm, upbeat and genuinely excited home-finding buddy for Homerun, a Singapore property app. You are on a live voice call with someone about to tell you about their dream home.

HOW YOU SOUND
- Talk like a real, friendly person, not a script. Short, natural sentences (usually 1-2). Quick reactions like "Ooh nice!", "Love that!", "Got it!". Warm, smiling energy. Never robotic, never read out lists or bullet points.
- Never mention tools, functions, forms, "fields" or "questions". It's just a chat.
- Speak English; a little Singlish warmth ("lah", "can!") is welcome only if the caller does it first.

HOW THE CALL GOES
1. You speak FIRST. As soon as the call starts, greet them in one or two bursts of energy, say you're Ava, and invite them to describe their dream home in their own words. Don't list what you need.
2. Let them talk. React briefly and genuinely to what they say.
3. Secretly you need four things: (a) maximum budget in SGD, (b) number of bedrooms, (c) property type — HDB, condo, EC (executive condominium) or landed, (d) preferred town/area in Singapore, or "anywhere".
4. The moment you hear ANY of these, call save_preferences with what you heard (don't announce it, keep talking naturally). Convert spoken amounts to plain numbers: "eight hundred k" -> 800000, "1.2 million" -> 1200000. If they say "up to 1 mil", budget is 1000000. Call it again whenever they change their mind or add detail.
5. save_preferences replies with what is still missing. Weave the missing items into the conversation ONE at a time, casually, like a friend would ("And roughly how many bedrooms are we thinking?"). Never ask about something they already told you. If an answer is vague ("something not too expensive"), ask for a rough number. If they say "3-room"/"4-room flat", clarify in bedrooms.
6. If they say they have no budget limit, or don't mind where, record that with no_budget_limit / anywhere_in_singapore.
7. When save_preferences says everything is answered, give a quick, excited one-sentence recap (budget, bedrooms, type, area) and tell them you're pulling up their matches right now. Then stop talking — the app takes over.

Known towns (use these exact names when they match): {", ".join(TOWNS)}. Other areas (e.g. Orchard) are fine too; pass them through as spoken.
Property types: {", ".join(PROPERTY_TYPES)}."""

START_CUE = "[The call just connected. Greet the caller now and start the conversation.]"

SAVE_TOOL = {
    "functionDeclarations": [
        {
            "name": "save_preferences",
            "description": (
                "Record the buyer's housing preferences exactly as heard. Call it every time you learn or "
                "update anything. Only include fields you actually learned."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "budget_sgd": {"type": "NUMBER", "description": "Maximum budget in SGD as a plain number."},
                    "no_budget_limit": {"type": "BOOLEAN", "description": "True if the buyer has no budget cap."},
                    "bedrooms": {
                        "type": "ARRAY",
                        "items": {"type": "INTEGER"},
                        "description": "Bedroom counts wanted, e.g. [3] or [3, 4]. 5 means 5 or more.",
                    },
                    "property_types": {
                        "type": "ARRAY",
                        "items": {"type": "STRING", "enum": PROPERTY_TYPES},
                        "description": "HDB, CONDO, EC (executive condo) or LANDED.",
                    },
                    "towns": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                        "description": "Preferred towns/areas in Singapore, e.g. ['TAMPINES', 'BISHAN'].",
                    },
                    "anywhere_in_singapore": {
                        "type": "BOOLEAN",
                        "description": "True if the buyer doesn't mind which town.",
                    },
                },
            },
        }
    ]
}


def build_setup(model: str, voice: str) -> dict[str, Any]:
    return {
        "setup": {
            "model": f"models/{model}",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
            },
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "tools": [SAVE_TOOL],
            "realtimeInputConfig": {
                # Snappy turn-taking: react quickly once the caller stops, and allow barge-in.
                "automaticActivityDetection": {
                    "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
                    "endOfSpeechSensitivity": "END_SENSITIVITY_HIGH",
                    "prefixPaddingMs": 80,
                    "silenceDurationMs": 450,
                },
                "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
            },
            "contextWindowCompression": {"slidingWindow": {}},
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }
    }


class VoiceSession:
    def __init__(self, browser: WebSocket, settings: Settings) -> None:
        self.browser = browser
        self.settings = settings
        self.prefs = VoicePreferences()
        self._gemini: Any = None
        self._finish_pending = False  # all four answered; finish after the assistant's recap audio
        self._audio_since_finish = False
        self._finished = False

    async def run(self) -> None:
        await self.browser.accept()
        if not self.settings.gemini_api_key:
            await self._send({"type": "error", "message": "Voice AI is not configured on the server."})
            await self.browser.close()
            return
        try:
            await self._connect()
        except Exception as exc:  # noqa: BLE001 - surface any upstream failure to the caller
            logger.error("voice_connect_failed error=%r", exc)
            await self._send({"type": "error", "message": "Couldn't reach the voice service. Please try again."})
            await self.browser.close()
            return

        await self._send({"type": "ready"})
        # realtimeInput.text is accepted by every Live model and triggers the assistant to speak first.
        await self._gemini.send(json.dumps({"realtimeInput": {"text": START_CUE}}))

        tasks = [
            asyncio.create_task(self._browser_to_gemini()),
            asyncio.create_task(self._gemini_to_browser()),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self._gemini.close()
            try:
                await self.browser.close()
            except RuntimeError:
                pass  # already closed

    async def _connect(self) -> None:
        headers = {"x-goog-api-key": self.settings.gemini_api_key or ""}
        last_exc: Exception | None = None
        for model in dict.fromkeys([self.settings.gemini_live_model, self.settings.gemini_live_fallback_model]):
            try:
                ws = await websockets.connect(
                    GEMINI_LIVE_URL, additional_headers=headers, max_size=None, ping_interval=20
                )
                await ws.send(json.dumps(build_setup(model, self.settings.gemini_live_voice)))
                reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if "setupComplete" not in reply:
                    raise RuntimeError(f"unexpected setup reply: {str(reply)[:200]}")
                self._gemini = ws
                logger.info("voice_session_started model=%s", model)
                return
            except Exception as exc:  # noqa: BLE001 - try the fallback model
                logger.warning("voice_model_failed model=%s error=%r", model, exc)
                last_exc = exc
        raise last_exc or RuntimeError("no voice model available")

    async def _send(self, payload: dict[str, Any]) -> None:
        await self.browser.send_text(json.dumps(payload))

    async def _browser_to_gemini(self) -> None:
        try:
            while True:
                msg = await self.browser.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                if msg.get("bytes"):
                    await self._gemini.send(json.dumps({
                        "realtimeInput": {"audio": {
                            "data": base64.b64encode(msg["bytes"]).decode(),
                            "mimeType": "audio/pcm;rate=16000",
                        }}
                    }))
                elif msg.get("text"):
                    ctl = json.loads(msg["text"])
                    if ctl.get("type") == "audio_end":  # mic muted: flush cached audio
                        await self._gemini.send(json.dumps({"realtimeInput": {"audioStreamEnd": True}}))
                    elif ctl.get("type") == "text" and str(ctl.get("text", "")).strip():
                        await self._gemini.send(json.dumps({"realtimeInput": {"text": str(ctl["text"])}}))
                    elif ctl.get("type") == "end":
                        return
        except (WebSocketDisconnect, websockets.ConnectionClosed):
            return

    async def _gemini_to_browser(self) -> None:
        try:
            async for raw in self._gemini:
                msg = json.loads(raw)
                if "toolCall" in msg:
                    await self._handle_tool_call(msg["toolCall"])
                if "serverContent" in msg:
                    await self._handle_server_content(msg["serverContent"])
                if "goAway" in msg:
                    await self._send({"type": "error", "message": "The voice session timed out."})
                    return
                if self._finished:
                    return
        except websockets.ConnectionClosed as exc:
            logger.warning("voice_gemini_closed code=%s", getattr(exc, "code", None))
            if not self._finished:
                await self._send({"type": "error", "message": "The voice connection dropped."})
        except WebSocketDisconnect:
            return

    async def _handle_tool_call(self, tool_call: dict[str, Any]) -> None:
        responses = []
        for call in tool_call.get("functionCalls", []):
            if call.get("name") != "save_preferences":
                responses.append({"id": call.get("id"), "name": call.get("name"),
                                  "response": {"error": "unknown function"}})
                continue
            self.prefs.update(call.get("args") or {})
            missing = self.prefs.missing()
            if missing:
                result = {
                    "status": "saved",
                    "still_missing": [QUESTION_LABELS[k] for k in missing],
                    "next_step": "Keep chatting naturally and ask about ONE missing item, if the caller hasn't "
                                 "already covered it. Don't repeat what they told you.",
                }
            else:
                result = {
                    "status": "all_answered",
                    "next_step": "Everything is captured. Give a quick, excited one-sentence recap and say "
                                 "you're pulling up their matches now. Don't ask any more questions.",
                }
                self._finish_pending, self._audio_since_finish = True, False
            responses.append({"id": call.get("id"), "name": "save_preferences", "response": result})
            await self._send({"type": "state", **self.prefs.snapshot()})
        await self._gemini.send(json.dumps({"toolResponse": {"functionResponses": responses}}))

    async def _handle_server_content(self, sc: dict[str, Any]) -> None:
        if sc.get("interrupted"):
            await self._send({"type": "interrupted"})
        for part in (sc.get("modelTurn") or {}).get("parts", []):
            inline = part.get("inlineData")
            if inline and inline.get("data"):
                if self._finish_pending:
                    self._audio_since_finish = True
                await self.browser.send_bytes(base64.b64decode(inline["data"]))
        if (t := (sc.get("inputTranscription") or {}).get("text")):
            await self._send({"type": "transcript", "role": "user", "text": t})
        if (t := (sc.get("outputTranscription") or {}).get("text")):
            await self._send({"type": "transcript", "role": "assistant", "text": t})
        if sc.get("turnComplete"):
            await self._send({"type": "turn_complete"})
            if self._finish_pending and self._audio_since_finish and self.prefs.complete:
                self._finished = True
                await self._send({"type": "complete", "profile": self.prefs.to_profile_payload(),
                                  **self.prefs.snapshot()})
