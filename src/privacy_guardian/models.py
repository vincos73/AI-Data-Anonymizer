from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    entity_type: str
    start: int
    end: int
    score: float
    source: str = "italian_rules"

    @property
    def text_range(self) -> str:
        return f"{self.start}-{self.end}"
