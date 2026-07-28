from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Sequence

from privacy_guardian.models import AnonymizationMode, Finding


@dataclass(frozen=True)
class OutputProvenance:
    revision: int
    mode: AnonymizationMode
    source_sha256: str
    selection_sha256: str
    total_findings: int
    included_findings: int
    output_format: str
    used_ocr: bool
    map_required: bool
    kind: str = "anonymized"

    @property
    def excluded_findings(self) -> int:
        return max(0, self.total_findings - self.included_findings)


def source_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def selection_fingerprint(findings: Sequence[Finding], included: Sequence[bool]) -> str:
    rows = [
        (
            finding.entity_type,
            finding.start,
            finding.end,
            finding.source,
            included[index] if index < len(included) else True,
        )
        for index, finding in enumerate(findings)
    ]
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()
