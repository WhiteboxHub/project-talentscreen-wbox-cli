"""Usage analytics event schema and sanitization helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


SENSITIVE_KEYS = {
    "password",
    "token",
    "api_key",
    "openai_api_key",
    "anthropic_api_key",
    "gemini_api_key",
    "resume",
    "resume_pdf_path",
    "resume_json_path",
}


class UsageEvent(BaseModel):
    """Canonical usage event payload."""

    user_id: str
    event_name: str
    event_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    command: Optional[str] = None
    result: Optional[str] = None
    duration_ms: Optional[int] = None
    jobs_attempted_count: Optional[int] = None
    jobs_submitted_count: Optional[int] = None
    jobs_failed_count: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Serialize for network transfer."""
        data = self.model_dump()
        data["event_ts"] = self.event_ts.isoformat()
        return sanitize_event_payload(data)


def sanitize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop sensitive fields from an event payload."""
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        lower = key.lower()
        if any(s in lower for s in SENSITIVE_KEYS):
            continue
        clean[key] = value
    md = clean.get("metadata")
    if isinstance(md, dict):
        clean["metadata"] = {
            k: v for k, v in md.items() if not any(s in k.lower() for s in SENSITIVE_KEYS)
        }
    return clean
