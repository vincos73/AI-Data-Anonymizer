from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast


AnonymizationMode = Literal["standard", "maximum", "reversible"]
ANONYMIZATION_MODES: tuple[AnonymizationMode, ...] = ("standard", "maximum", "reversible")


def validate_anonymization_mode(mode: str) -> AnonymizationMode:
    if mode in ANONYMIZATION_MODES:
        return cast(AnonymizationMode, mode)
    raise ValueError(f"Modalità anonimizzazione non supportata: {mode}")


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
