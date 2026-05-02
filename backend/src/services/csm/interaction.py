"""Interaction — registro pareado de uma troca bot↔user.

Diferente de aia_health_sofia_messages (todas mensagens, qualquer role),
Interaction grava UMA troca pareada: a pergunta da Sofia + a resposta do
user + os dados extraídos dessa resposta.

Use case central: "Sofia, lembre que perguntei X e o user respondeu Y,
e disso saiu o dado Z." Resolve o bug Douglas (3× Quantos idosos).

Stored in: aia_health_conversation_state.interactions JSONB array.
Janela mantida: últimas 30 (FIFO).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from src.services.csm.flow_state import QuestionIntent


@dataclass
class Interaction:
    """Uma troca pareada bot↔user."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: float = field(default_factory=time.time)

    # Bot side
    bot_message: Optional[str] = None
    bot_intent: Optional[QuestionIntent] = None  # intent da pergunta
    bot_agent: Optional[str] = None              # qual sub-agent gerou

    # User side
    lead_message: Optional[str] = None

    # Extração
    extracted_data: dict[str, Any] = field(default_factory=dict)
    extraction_confidence: float = 0.0  # 0..1

    # Tracking
    answered: bool = False  # True se lead_message preenchido pareando bot_message

    # ─── Persistência ────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Interaction":
        intent = data.get("bot_intent")
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            ts=float(data.get("ts") or time.time()),
            bot_message=data.get("bot_message"),
            bot_intent=QuestionIntent(intent) if intent else None,
            bot_agent=data.get("bot_agent"),
            lead_message=data.get("lead_message"),
            extracted_data=data.get("extracted_data") or {},
            extraction_confidence=float(data.get("extraction_confidence") or 0.0),
            answered=bool(data.get("answered", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "ts": self.ts,
            "answered": self.answered,
        }
        if self.bot_message:
            out["bot_message"] = self.bot_message
        if self.bot_intent:
            out["bot_intent"] = self.bot_intent.value
        if self.bot_agent:
            out["bot_agent"] = self.bot_agent
        if self.lead_message:
            out["lead_message"] = self.lead_message
        if self.extracted_data:
            out["extracted_data"] = self.extracted_data
        if self.extraction_confidence:
            out["extraction_confidence"] = self.extraction_confidence
        return out

    # ─── Helpers ─────────────────────────────────────────────────

    def attach_user_response(
        self,
        user_text: str,
        *,
        extracted: Optional[dict[str, Any]] = None,
        confidence: float = 0.0,
    ) -> None:
        """Marca que o user respondeu a essa interaction."""
        self.lead_message = user_text
        self.answered = True
        if extracted:
            self.extracted_data.update(extracted)
        if confidence:
            self.extraction_confidence = max(self.extraction_confidence, confidence)
