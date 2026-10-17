"""``WS /api/voice/ws``: real-time voice assistant that gathers the four buyer preferences
(budget, bedrooms, property type, town) through conversation. See ``VoiceSession``."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.core.config import get_settings
from app.services.voice_session import VoiceSession

router = APIRouter(tags=["voice"])


@router.websocket("/voice/ws")
async def voice_ws(websocket: WebSocket) -> None:
    await VoiceSession(websocket, get_settings()).run()
