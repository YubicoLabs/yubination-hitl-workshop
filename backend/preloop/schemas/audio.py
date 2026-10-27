"""Schemas for server-side audio fallback endpoints."""

import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SpeechToTextResponse(BaseModel):
    """Transcript returned from a resolved STT model."""

    text: str
    ai_model_id: uuid.UUID
    provider_name: str
    model_identifier: str


class TextToSpeechRequest(BaseModel):
    """Text payload for server-side TTS fallback."""

    input: str = Field(..., min_length=1, max_length=16000)
    voice: str = Field("alloy", min_length=1, max_length=100)
    response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "mp3"
    ai_model_id: Optional[uuid.UUID] = None
