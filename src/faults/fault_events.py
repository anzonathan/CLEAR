"""Shared event types for tennis fault decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


FaultType = Literal[
    "foot_fault",
    "service_fault",
    "net_fault",
    "let",
]

FaultStatus = Literal[
    "fault",
    "no_fault",
    "uncertain",
]


@dataclass(frozen=True)
class FaultEvent:
    """Result of evaluating one potential tennis fault."""

    fault_type: FaultType
    status: FaultStatus
    frame_idx: int
    reason: str
    confidence: float = 1.0
    player_id: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "fault_type": self.fault_type,
            "status": self.status,
            "frame_idx": self.frame_idx,
            "reason": self.reason,
            "confidence": round(
                max(0.0, min(1.0, self.confidence)), 3
            ),
            "player_id": self.player_id,
        }
