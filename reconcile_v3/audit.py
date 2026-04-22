"""Hypothesis tracing — every emitted element records why it exists."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HypothesisTrace:
    stage: str
    rule: str
    inputs: dict[str, Any] = field(default_factory=dict)
    decision_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "rule": self.rule,
            "inputs": dict(self.inputs),
            "decision_reason": self.decision_reason,
        }


@dataclass
class AuditLog:
    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, element_id: str, trace: HypothesisTrace) -> None:
        self.entries.append({"element_id": element_id, **trace.to_dict()})

    def to_list(self) -> list[dict[str, Any]]:
        return list(self.entries)
