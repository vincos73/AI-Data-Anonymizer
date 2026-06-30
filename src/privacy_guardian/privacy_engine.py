from __future__ import annotations

from typing import Iterable

from privacy_guardian import __version__
from privacy_guardian.italian_privacy_engine import ItalianPrivacyRecognizer
from privacy_guardian.models import AnonymizationMode, Finding, validate_anonymization_mode


class PrivacyEngine:
    """Italian-first privacy engine for local anonymization."""

    def __init__(self) -> None:
        self._recognizer = ItalianPrivacyRecognizer()
        self.status = f"v{__version__}"

    def analyze(self, text: str, mode: AnonymizationMode | str = "standard") -> list[Finding]:
        return self._recognizer.analyze(text, validate_anonymization_mode(mode))

    def anonymize(
        self,
        text: str,
        findings: Iterable[Finding] | None = None,
        mode: AnonymizationMode | str = "standard",
    ) -> str:
        mode = validate_anonymization_mode(mode)
        findings = list(findings if findings is not None else self.analyze(text, mode))
        return self._recognizer.anonymize(text, findings, mode)
