from __future__ import annotations

import os

from privacy_guardian.models import Finding


NER_MODELS = ("it_core_news_lg", "it_core_news_md", "it_core_news_sm")
NER_ENV_FLAG = "OMISSIS_NER"
NER_SCORE = 0.7


class NerPersonRecognizer:
    """Optional local spaCy NER for person names the regex rules cannot see.

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
            if entity.label_ != "PER":
                continue
            name = entity.text.strip()
            if not self._looks_like_full_name(name):
                continue
            end = entity.start_char + len(entity.text.rstrip())
            findings.append(Finding("PERSON", entity.start_char, end, NER_SCORE, source="ner_local"))
        return findings

    def _looks_like_full_name(self, name: str) -> bool:
        words = name.split()
        return len(words) >= 2 and all(word[0].isupper() for word in words)
