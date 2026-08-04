from __future__ import annotations

import os

from privacy_guardian.italian_locations import (
    contains_address_marker,
    is_legal_ner_false_positive,
    should_accept_ner_location,
)
from privacy_guardian.models import Finding


NER_MODELS = ("it_core_news_lg", "it_core_news_md", "it_core_news_sm")
NER_ENV_FLAG = "OMISSIS_NER"
NER_SCORE = 0.7
NER_LOCATION_SCORE = 0.78


class NerPersonRecognizer:
    """Optional local spaCy NER for people and locations the rules cannot see.

    Enabled only when spaCy and an Italian model are installed; everything runs
    on the local machine, no external services. Set OMISSIS_NER=0 to disable.
    """

    def __init__(self, nlp) -> None:
        self._nlp = nlp

    @classmethod
    def create_if_available(cls) -> NerPersonRecognizer | None:
        if os.environ.get(NER_ENV_FLAG, "").strip().lower() in {"0", "false", "off", "no"}:
            return None
        try:
            import spacy
        except ImportError:
            return None

        for model_name in NER_MODELS:
            try:
                return cls(spacy.load(model_name))
            except OSError:
                continue
        return None

    def analyze(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for entity in self._nlp(text).ents:
            value = entity.text.strip()
            leading_space = len(entity.text) - len(entity.text.lstrip())
            start = entity.start_char + leading_space
            end = entity.start_char + len(entity.text.rstrip())
            if entity.label_ == "PER":
                if self._looks_like_full_name(value):
                    findings.append(Finding("PERSON", start, end, NER_SCORE, source="ner_local"))
                continue
            if entity.label_ in {"LOC", "GPE"} and should_accept_ner_location(
                text, start, end, value
            ):
                findings.append(
                    Finding("LOCATION", start, end, NER_LOCATION_SCORE, source="ner_local")
                )
        return findings

    def _looks_like_full_name(self, name: str) -> bool:
        words = name.split()
        return (
            len(words) >= 2
            and not is_legal_ner_false_positive(name)
            and not contains_address_marker(name)
            and all(self._is_name_word(word) for word in words)
        )

    @staticmethod
    def _is_name_word(word: str) -> bool:
        """Accept normal name punctuation but reject merged CSV/email tokens."""
        normalized = word.replace("-", "").replace("'", "").replace("’", "")
        return bool(normalized) and word[0].isupper() and normalized.isalpha()
