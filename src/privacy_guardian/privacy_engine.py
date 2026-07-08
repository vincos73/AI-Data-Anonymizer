from __future__ import annotations

from typing import Iterable

from privacy_guardian import __version__
from privacy_guardian.italian_privacy_engine import ItalianPrivacyRecognizer
from privacy_guardian.models import AnonymizationMode, Finding, validate_anonymization_mode
from privacy_guardian.ner_recognizer import NerPersonRecognizer
from privacy_guardian.reversible import ReversibleAnonymizationResult, reversible_anonymize


class PrivacyEngine:
    """Italian-first privacy engine for local anonymization."""

    def __init__(self) -> None:
        self._recognizer = ItalianPrivacyRecognizer()
        self._ner = NerPersonRecognizer.create_if_available()
        self.status = f"v{__version__} · NER locale attivo" if self._ner else f"v{__version__}"

    def analyze(self, text: str, mode: AnonymizationMode | str = "standard") -> list[Finding]:
        findings = self._recognizer.analyze(text, validate_anonymization_mode(mode))
        if self._ner:
            findings = self._recognizer.dedupe(findings + self._ner.analyze(text))
        return self._recognizer.propagate_person_coreferences(text, findings)

    def anonymize(
        self,
        text: str,
        findings: Iterable[Finding] | None = None,
        mode: AnonymizationMode | str = "standard",
    ) -> str:
        mode = validate_anonymization_mode(mode)
        findings = list(findings if findings is not None else self.analyze(text, mode))
        if mode == "reversible":
            return reversible_anonymize(text, findings).text
        return self._recognizer.anonymize(text, findings, mode)

    def anonymize_reversible(
        self,
        text: str,
        findings: Iterable[Finding] | None = None,
    ) -> ReversibleAnonymizationResult:
        findings = list(findings if findings is not None else self.analyze(text, "reversible"))
        return reversible_anonymize(text, findings)
