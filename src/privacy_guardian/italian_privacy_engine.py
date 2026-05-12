from __future__ import annotations

import re

from privacy_guardian.models import Finding

LETTER = r"A-Za-zÀ-ÖØ-öø-ÿ"
CAPITAL_WORD = rf"[A-ZÀ-ÖØ-Þ][{LETTER}'’.-]+"
ORG_WORD = rf"(?:[A-ZÀ-ÖØ-Þ0-9][{LETTER}0-9&'’.-]*|[A-Z0-9&]{{2,}})"
PREFIX_ORG_WORD = rf"(?:[A-ZÀ-ÖØ-Þ][{LETTER}&'’-]*|[A-Z0-9&]{{2,}})"


class ItalianPrivacyRecognizer:
    """High-precision recognizers for common Italian privacy data."""

    EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.IGNORECASE)
    CODICE_FISCALE = re.compile(
        r"\b[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]\b",
        re.IGNORECASE,
    )
    PARTITA_IVA = re.compile(r"\b(?:IT[\s-]?)?([0-9]{11})\b", re.IGNORECASE)
    IBAN = re.compile(r"\bIT[0-9]{2}[A-Z][0-9]{10}[A-Z0-9]{12}\b", re.IGNORECASE)
    PHONE_NUMBER = re.compile(
        r"(?<!\w)(?:\+39[\s.-]?)?(?:3[0-9]{2}|0[0-9]{1,4})[\s.-]?[0-9]{3,4}[\s.-]?[0-9]{3,4}(?!\w)"
    )
    ADDRESS = re.compile(
        rf"\b(?i:via|v\.|viale|v\.le|piazza|p\.zza|piazzale|corso|c\.so|vicolo|largo|strada|contrada|"
        rf"localit[aà]|loc\.|frazione)\s+"
        rf"(?:{CAPITAL_WORD}|[A-Z0-9]{{1,5}})(?:\s+(?:{CAPITAL_WORD}|[a-zà-öø-ÿ]{{2,}}|[A-Z0-9]{{1,5}})){{0,7}}"
        rf"(?:\s*,?\s+\d{{1,4}}[A-Za-z]?)?"
        rf"(?:\s*,?\s*(?:\d{{5}}\s+)?{CAPITAL_WORD}(?:\s+{CAPITAL_WORD}){{0,2}})?",
    )
    COMPANY_SUFFIX = re.compile(
        rf"\b(?:{ORG_WORD}(?:\s+|$)){{1,8}}"
        r"(?i:s\.?\s*r\.?\s*l\.?|s\.?\s*p\.?\s*a\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*a\.?\s*s\.?|"
        r"soc\.?\s*coop\.?|cooperativa|onlus|aps|ets|s\.?\s*s\.?)"
        r"(?!\w)",
    )
    COMPANY_PREFIX = re.compile(
        rf"\b(?i:ditta(?:\s+individuale)?|societ[aà]|impresa|azienda|ragione\s+sociale|denominazione|cooperativa)"
        rf"\s+(?:{PREFIX_ORG_WORD}(?:\s+|$)){{1,6}}"
        r"(?:(?i:s\.?\s*r\.?\s*l\.?|s\.?\s*p\.?\s*a\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*a\.?\s*s\.?|"
        r"soc\.?\s*coop\.?|cooperativa|onlus|aps|ets|s\.?\s*s\.?)\b)?",
    )
    PERSON = re.compile(
        rf"\b(?:(?:il|la)\s+)?"
        r"(?i:sig\.?ra?|signora|signor|dott\.?ssa|dott\.?|avv\.?|ing\.?|geom\.?|rag\.?|"
        r"prof\.?ssa|prof\.?|sottoscritto|sottoscritta|cliente|referente|rappresentante|"
        r"titolare|nato|nata)\s+"
        rf"(?P<name>{CAPITAL_WORD}(?:\s+{CAPITAL_WORD}){{1,3}})",
    )
    TERRITORIAL_BODY = re.compile(
        rf"\b(?i:provincia|regione|comune|citt[aà]\s+metropolitana|municipio|unione\s+dei\s+comuni|"
        rf"comunit[aà]\s+montana)\s+(?:(?:di|del|della|dei|degli|delle)\s+)?"
        rf"{CAPITAL_WORD}(?:\s+{CAPITAL_WORD}){{0,4}}"
    )
    PERSON_STOPWORDS = {
        "Premesso",
        "Contratto",
        "Societa",
        "Società",
        "Impresa",
        "Azienda",
        "Ditta",
        "Cliente",
        "Referente",
        "Rappresentante",
        "Sottoscritto",
        "Sottoscritta",
        "Nato",
        "Nata",
    }

    def analyze(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._regex_findings(text, "EMAIL_ADDRESS", self.EMAIL, 0.98))
        findings.extend(self._regex_findings(text, "PHONE_NUMBER", self.PHONE_NUMBER, 0.94))
        findings.extend(self._codice_fiscale_findings(text))
        findings.extend(self._partita_iva_findings(text))
        findings.extend(self._iban_findings(text))
        findings.extend(self._regex_findings(text, "ADDRESS", self.ADDRESS, 0.86))
        findings.extend(self._organization_findings(text))
        findings.extend(self._territorial_body_findings(text))
        findings.extend(self._person_findings(text))
        return self._dedupe(findings)

    def anonymize(self, text: str, findings: list[Finding] | None = None) -> str:
        findings = findings if findings is not None else self.analyze(text)
        chunks: list[str] = []
        cursor = 0

        for finding in sorted(findings, key=lambda item: item.start):
            chunks.append(text[cursor : finding.start])
            chunks.append(self._replacement(text[finding.start : finding.end], finding.entity_type))
            cursor = finding.end

        chunks.append(text[cursor:])
        return "".join(chunks)

    def _regex_findings(
        self,
        text: str,
        entity_type: str,
        pattern: re.Pattern[str],
        score: float,
        *,
        trim_period: bool = True,
    ) -> list[Finding]:
        return [
            Finding(entity_type, match.start(), self._trim_end(text, match.end(), trim_period=trim_period), score)
            for match in pattern.finditer(text)
            if self._trim_end(text, match.end(), trim_period=trim_period) > match.start()
        ]

    def _codice_fiscale_findings(self, text: str) -> list[Finding]:
        return [
            Finding("CODICE_FISCALE", match.start(), match.end(), 0.96)
            for match in self.CODICE_FISCALE.finditer(text)
            if self._valid_codice_fiscale(match.group(0).upper())
        ]

    def _partita_iva_findings(self, text: str) -> list[Finding]:
        return [
            Finding("PARTITA_IVA", match.start(), match.end(), 0.96)
            for match in self.PARTITA_IVA.finditer(text)
            if self._valid_partita_iva(match.group(1))
        ]

    def _iban_findings(self, text: str) -> list[Finding]:
        return [
            Finding("IBAN", match.start(), match.end(), 0.97)
            for match in self.IBAN.finditer(text)
            if self._valid_iban(match.group(0).upper())
        ]

    def _organization_findings(self, text: str) -> list[Finding]:
        findings = self._regex_findings(text, "ORGANIZATION", self.COMPANY_SUFFIX, 0.9, trim_period=False)
        findings.extend(self._regex_findings(text, "ORGANIZATION", self.COMPANY_PREFIX, 0.88, trim_period=False))
        return [finding for finding in findings if self._looks_like_organization(text[finding.start : finding.end])]

    def _territorial_body_findings(self, text: str) -> list[Finding]:
        return self._regex_findings(text, "TERRITORIAL_BODY", self.TERRITORIAL_BODY, 0.88)

    def _person_findings(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for match in self.PERSON.finditer(text):
            name = match.group("name").strip()
            words = name.split()
            if len(words) < 2 or any(word.strip(" .") in self.PERSON_STOPWORDS for word in words):
                continue
            findings.append(Finding("PERSON", match.start("name"), match.end("name"), 0.84))
        return findings

    def _dedupe(self, findings: list[Finding]) -> list[Finding]:
        priority = {
            "CODICE_FISCALE": 7,
            "PARTITA_IVA": 7,
            "IBAN": 7,
            "EMAIL_ADDRESS": 7,
            "PHONE_NUMBER": 7,
            "ORGANIZATION": 6,
            "TERRITORIAL_BODY": 6,
            "PERSON": 5,
            "ADDRESS": 4,
        }
        ordered = sorted(
            findings,
            key=lambda item: (
                item.start,
                -(item.end - item.start),
                -priority.get(item.entity_type, 0),
                -item.score,
            ),
        )
        kept: list[Finding] = []

        for finding in ordered:
            if not any(finding.start < existing.end and existing.start < finding.end for existing in kept):
                kept.append(finding)

        return sorted(kept, key=lambda item: item.start)

    def _looks_like_organization(self, value: str) -> bool:
        normalized = re.sub(r"\s+", " ", value.strip()).lower()
        if normalized in {"società", "societa", "impresa", "azienda", "ditta", "cooperativa"}:
            return False
        has_suffix = bool(
            re.search(
                r"\b(s\.?\s*r\.?\s*l\.?|s\.?\s*p\.?\s*a\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*a\.?\s*s\.?|"
                r"soc\.?\s*coop\.?|cooperativa|onlus|aps|ets|s\.?\s*s\.?)\b",
                normalized,
            )
        )
        has_prefix = bool(re.match(r"(ditta|societ[aà]|impresa|azienda|ragione sociale|denominazione|cooperativa)\b", normalized))
        return has_suffix or has_prefix

    def _trim_end(self, text: str, end: int, *, trim_period: bool) -> int:
        chars = " ,;:." if trim_period else " ,;:"
        while end > 0 and text[end - 1] in chars:
            end -= 1
        return end

    def _valid_iban(self, iban: str) -> bool:
        rearranged = iban[4:] + iban[:4]
        numeric = "".join(str(ord(char) - 55) if char.isalpha() else char for char in rearranged)
        return int(numeric) % 97 == 1

    def _valid_partita_iva(self, value: str) -> bool:
        if len(value) != 11 or not value.isdigit():
            return False

        total = 0
        for index, char in enumerate(value[:10]):
            digit = int(char)
            if index % 2 == 0:
                total += digit
            else:
                doubled = digit * 2
                total += doubled if doubled < 10 else doubled - 9

        return (10 - total % 10) % 10 == int(value[-1])

    def _valid_codice_fiscale(self, value: str) -> bool:
        odd = {
            **dict.fromkeys("0A", 1),
            **dict.fromkeys("1B", 0),
            **dict.fromkeys("2C", 5),
            **dict.fromkeys("3D", 7),
            **dict.fromkeys("4E", 9),
            **dict.fromkeys("5F", 13),
            **dict.fromkeys("6G", 15),
            **dict.fromkeys("7H", 17),
            **dict.fromkeys("8I", 19),
            **dict.fromkeys("9J", 21),
            "K": 2,
            "L": 4,
            "M": 18,
            "N": 20,
            "O": 11,
            "P": 3,
            "Q": 6,
            "R": 8,
            "S": 12,
            "T": 14,
            "U": 16,
            "V": 10,
            "W": 22,
            "X": 25,
            "Y": 24,
            "Z": 23,
        }
        even = {str(number): number for number in range(10)}
        even.update({chr(ord("A") + number): number for number in range(26)})
        total = 0

        try:
            for index, char in enumerate(value[:15]):
                total += odd[char] if index % 2 == 0 else even[char]
        except KeyError:
            return False

        return chr(ord("A") + total % 26) == value[-1]

    def _replacement(self, value: str, entity_type: str) -> str:
        if entity_type in {"PERSON", "ORGANIZATION", "TERRITORIAL_BODY", "ADDRESS"}:
            return self._initials(value)
        return f"<{entity_type}>"

    def _initials(self, value: str) -> str:
        tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", value)
        initials = [f"{token[0]}." for token in tokens if token and not token.isdigit()]
        return " ".join(initials) if initials else "<ANONYMIZED>"
