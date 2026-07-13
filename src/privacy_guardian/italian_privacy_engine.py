from __future__ import annotations

import re

from privacy_guardian.first_names import is_italian_first_name
from privacy_guardian.models import AnonymizationMode, Finding
from privacy_guardian.reporting import entity_placeholder

LETTER = r"A-Za-zÀ-ÖØ-öø-ÿ"
CAPITAL_WORD = rf"[A-ZÀ-ÖØ-Þ][{LETTER}'’.-]+"
STREET_KEYWORD = r"(?:Via|Viale|Piazza|Piazzale|Corso|Largo|Vicolo|Strada|Contrada|Località|Localita|Frazione)"
CAPITAL_NAME_WORD = rf"(?!{STREET_KEYWORD}\b){CAPITAL_WORD}"
LOWER_ADDRESS_WORD = r"[a-zà-öø-ÿ]{2,}"
ORG_WORD = rf"(?:[A-ZÀ-ÖØ-Þ0-9][{LETTER}0-9&'’.-]*|[A-Z0-9&]{{2,}}|&)"
PREFIX_ORG_WORD = rf"(?:[A-ZÀ-ÖØ-Þ][{LETTER}&'’-]*|[A-Z0-9&]{{2,}}|&)"
EMAIL_VALUE = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"

# Official IBAN lengths by country code (ISO 13616 registry).
IBAN_LENGTHS = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22,
    "BH": 22, "BR": 29, "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22, "DK": 18,
    "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18, "FO": 18, "FR": 27, "GB": 22,
    "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HR": 21, "HU": 28, "IE": 22,
    "IL": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28, "LI": 21,
    "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MD": 24, "ME": 22, "MK": 19, "MT": 31,
    "MU": 30, "NL": 18, "NO": 15, "PK": 24, "PL": 28, "PS": 29, "PT": 25, "QA": 29,
    "RO": 24, "RS": 22, "SA": 24, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "TN": 24,
    "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
}


class ItalianPrivacyRecognizer:
    """High-precision recognizers for common Italian privacy data."""

    EMAIL = re.compile(rf"\b{EMAIL_VALUE}\b", re.IGNORECASE)
    PEC_CONTEXT = re.compile(
        rf"\b(?i:pec|posta\s+elettronica\s+certificata|domicilio\s+digitale)"
        rf"\s*(?i:n\.?|num\.?|nr\.?|indirizzo|email|e-mail)?\s*[:#-]?\s*"
        rf"(?P<email>{EMAIL_VALUE})\b",
        re.IGNORECASE,
    )
    CODICE_FISCALE = re.compile(
        r"\b[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]\b",
        re.IGNORECASE,
    )
    PARTITA_IVA = re.compile(r"\b(?:IT[\s-]?)?([0-9]{11})\b", re.IGNORECASE)
    IBAN = re.compile(r"\b[A-Z]{2}[\s-]*[0-9]{2}(?:[\s-]*[A-Z0-9]){11,30}\b", re.IGNORECASE)
    PHONE_NUMBER = re.compile(
        r"(?<!\w)(?:\+39[\s./-]?)?(?:3[0-9]{2}|0[0-9]{1,4})[\s./-]?[0-9]{3,4}[\s./-]?[0-9]{3,4}(?!\w)"
    )
    INTERNATIONAL_PHONE = re.compile(
        r"(?<![\w+])\+(?!39\b)[1-9][0-9]{0,2}(?:[\s./-]?\(?[0-9]{1,4}\)?){2,5}(?!\w)"
    )
    SDI_CODE = re.compile(
        r"\b(?i:codice\s+(?:destinatario(?:\s+sdi)?|sdi|univoco(?:\s+ufficio)?)|"
        r"cod\.?\s*(?:destinatario|sdi|univoco)|sdi)"
        r"\s*(?i:n\.?|num\.?|nr\.?|numero|cod\.?)?\s*[:#-]?\s*"
        r"(?P<sdi>[A-Z0-9]{6,7})\b",
        re.IGNORECASE,
    )
    HEALTH_CARD = re.compile(
        r"\b(?i:(?:(?:numero|codice|cod\.?)\s+(?:della\s+)?)?tessera\s+sanitaria|"
        r"ts[\s-]*cns|carta\s+nazionale\s+dei\s+servizi)"
        r"\s*(?i:n\.?|num\.?|nr\.?|numero|codice|cod\.?)?\s*[:#-]?\s*"
        r"(?P<card>(?:\d[\s.-]?){19}\d)\b",
        re.IGNORECASE,
    )
    IDENTITY_DOCUMENT = re.compile(
        r"\b(?i:carta\s+d['’]?\s*identit[aà]|carta\s+identit[aà]|documento\s+d['’]?\s*identit[aà]|"
        r"documento\s+identit[aà]|passaporto|patente|c\.?\s*i\.?)"
        r"\s*(?i:n\.?|num\.?|nr\.?|numero)?\s*[:#-]?\s*"
        r"(?P<document>[A-Z]{1,3}[\s.-]?\d{4,8}[\s.-]?[A-Z]{0,3}|\d{6,10})\b",
        re.IGNORECASE,
    )
    VEHICLE_PLATE = re.compile(
        r"\b(?i:targa(?:\s+(?:veicolo|auto|autovettura|aziendale)){0,3}|targato|targata|"
        r"veicolo\s+targato|auto\s+targata|autovettura\s+targata)"
        r"\s*(?i:n\.?|num\.?|nr\.?|numero)?\s*[:#-]?\s*"
        r"(?P<plate>[A-Z]{2}\s*\d{3}\s*[A-Z]{2}|[A-Z]{1,2}\s*\d{5,6}|[A-Z]{2}\s*\d{5})\b",
        re.IGNORECASE,
    )
    PROTOCOL_CASE_NUMBER = re.compile(
        r"\b(?i:numero\s+(?:di\s+)?protocollo|protocollo(?:\s+informatico)?|prot\.?|"
        r"numero\s+(?:di\s+)?pratica|pratica|fascicolo|istanza|domanda|richiesta)"
        r"(?:\s+(?i:n\.?|num\.?|nr\.?|numero|cod\.?|codice|id))?\s*[:#-]?\s*"
        r"(?P<case>(?:[A-Z]{1,5}\s+)?[A-Z0-9]{2,}(?:\s*[./-]\s*[A-Z0-9]{1,10}){0,4})\b",
        re.IGNORECASE,
    )
    DATE = re.compile(
        r"(?<!\d)(?:[0-3]?\d)[/\-.](?:0?\d|1[0-2])[/\-.](?:\d{2}|\d{4})(?!\d)"
        r"|(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)"
        r"|\b(?:[0-3]?\d)\s+"
        r"(?i:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)"
        r"\s+(?:\d{2}|\d{4})\b"
    )
    ADDRESS = re.compile(
        rf"\b(?i:via|v\.|viale|v\.le|piazza|p\.zza|piazzale|corso|c\.so|vicolo|largo|strada|contrada|"
        rf"localit[aà]|loc\.|frazione)\s+"
        rf"(?:{CAPITAL_WORD}|[A-Z0-9]{{1,5}})(?:\s+(?:{CAPITAL_WORD}|[a-zà-öø-ÿ]{{2,}}|[A-Z0-9]{{1,5}})){{0,7}}"
        # (?![0-9]) impedisce al civico di fermarsi a metà di un CAP a 5 cifre
        # ("45, 00185 Roma" non deve diventare "45, 0018" lasciando "5 Roma" in chiaro)
        rf"(?:\s*,?\s+\d{{1,4}}(?![0-9])[A-Za-z]?)?"
        rf"(?:\s*,?\s*(?:\d{{5}}\s+)?{CAPITAL_WORD}(?:\s+{CAPITAL_WORD}){{0,2}})?",
    )
    ADDRESS_LOWERCASE = re.compile(
        rf"\b(?:via|viale|piazza|piazzale|corso|vicolo|largo|strada|contrada|frazione|località|localita)\s+"
        rf"(?P<name>{LOWER_ADDRESS_WORD}(?:\s+{LOWER_ADDRESS_WORD}){{0,3}})"
        rf"\s*,?\s+n?\.?\s*\d{{1,4}}(?:\s*/\s*[A-Za-z]|[A-Za-z])?\b"
    )
    ADDRESS_NAME_STOPWORDS = {
        "email", "e-mail", "mail", "pec", "fax", "sms", "telefono", "telematica", "posta",
        "preliminare", "definitiva", "ordinaria", "breve", "libera", "eccezionale", "prioritaria",
        "entro", "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "al", "allo", "alla",
        "ai", "agli", "alle", "per", "con", "presso", "ogni", "senza", "che", "numero", "corriere",
    }
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
        r"(?i:sig\.?ra|sig\.?|signora|signor|dott\.?ssa|dott\.?|avv\.?|ing\.?|geom\.?|rag\.?|"
        r"prof\.?ssa|prof\.?|sottoscritto|sottoscritta|cliente|referente|rappresentante|"
        r"titolare|nato|nata|intestatario|intestataria|intestato\s+a|intestata\s+a|"
        r"beneficiario|beneficiaria)\s+"
        rf"(?P<name>{CAPITAL_NAME_WORD}(?:\s+{CAPITAL_NAME_WORD}){{1,3}})",
    )
    CREDIT_CARD = re.compile(r"(?<![\w-])(?!0)\d(?:[ -]?\d){12,18}(?![\w-])")
    POSTAL_CODE_CITY = re.compile(
        r"\b(?P<cap>\d{5})\s+(?P<city>[A-ZÀ-Ù][a-zà-ù]+(?:\s+[A-ZÀ-Ù][a-zà-ù]+){0,3})\b"
    )
    MONTH_NAMES = {
        "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
        "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
    }
    POSTAL_CITY_STOPWORDS = {
        "Euro", "Eur", "Dollari", "Sterline", "Franchi",
        "Iva", "Netti", "Lordi", "Abitanti", "Unita", "Unità",
    }
    PERSON_TRAILING_CONTEXT = re.compile(
        rf"\b(?P<name>{CAPITAL_NAME_WORD}(?:\s+{CAPITAL_NAME_WORD}){{1,3}})\b"
        r"(?=\s*,?\s+(?i:nato|nata|residente|domiciliato|domiciliata|codice\s+fiscale|"
        r"c\.?\s*f\.?|email|e-mail|pec|tel\.?|telefono|cell\.?|cellulare)\b)"
    )
    # Candidati "nome proprio" senza contesto forte: la scansione parte da ogni parola
    # capitalizzata che sia un nome di battesimo italiano noto (dizionario locale, vedi
    # first_names.py) e prova a estendere da lì. Ancorarsi al nome — invece che a una
    # generica sequenza di maiuscole — evita che una maiuscola precedente non-nome
    # ("Repubblica Sergio Mattarella") consumi il candidato e nasconda la persona.
    CAPITAL_NAME_TOKEN = re.compile(rf"\b{CAPITAL_NAME_WORD}\b")
    DICTIONARY_PERSON_FROM_NAME = re.compile(rf"{CAPITAL_NAME_WORD}(?:\s+{CAPITAL_NAME_WORD}){{1,3}}\b")
    # Le strade italiane intitolate a persone ("via Mario Rossi") non devono diventare
    # PERSON: se il candidato è preceduto a breve distanza da un toponimo stradale,
    # viene scartato (il dedupe con ADDRESS copre già il caso con civico).
    STREET_PRECEDING_GUARD = re.compile(rf"{STREET_KEYWORD}\s*$", re.IGNORECASE)
    DICTIONARY_PERSON_SCORE = 0.72
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
    COREFERENCE_SCORE = 0.75
    KEYWORD_VOCABULARY = {
        "via", "viale", "piazza", "piazzale", "corso", "largo", "vicolo", "strada",
        "contrada", "localita", "località", "frazione",
        "provincia", "regione", "comune", "municipio",
        "sig", "sigra", "signora", "signor", "dott", "dottssa", "avv", "ing", "geom",
        "rag", "prof", "profssa", "sottoscritto", "sottoscritta", "cliente", "referente",
        "rappresentante", "titolare", "nato", "nata", "intestatario", "intestataria",
        "beneficiario", "beneficiaria",
        "srl", "spa", "snc", "sas", "soccoop", "cooperativa", "onlus", "aps", "ets",
        "ditta", "societa", "società", "impresa", "azienda", "denominazione",
    }

    def analyze(self, text: str, mode: AnonymizationMode = "standard") -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._regex_findings(text, "EMAIL_ADDRESS", self.EMAIL, 0.98))
        findings.extend(self._pec_email_findings(text))
        findings.extend(self._regex_findings(text, "PHONE_NUMBER", self.PHONE_NUMBER, 0.94))
        findings.extend(self._international_phone_findings(text))
        findings.extend(self._codice_fiscale_findings(text))
        findings.extend(self._partita_iva_findings(text))
        findings.extend(self._iban_findings(text))
        findings.extend(self._sdi_code_findings(text))
        findings.extend(self._health_card_findings(text))
        findings.extend(self._identity_document_findings(text))
        findings.extend(self._vehicle_plate_findings(text))
        findings.extend(self._protocol_case_findings(text))
        findings.extend(self._credit_card_findings(text))
        findings.extend(self._regex_findings(text, "ADDRESS", self.ADDRESS, 0.86))
        findings.extend(self._lowercase_address_findings(text))
        findings.extend(self._postal_code_city_findings(text))
        findings.extend(self._organization_findings(text))
        findings.extend(self._territorial_body_findings(text))
        findings.extend(self._person_findings(text))
        findings.extend(self._dictionary_person_findings(text))
        if mode in {"maximum", "reversible"}:
            findings.extend(self._regex_findings(text, "DATE", self.DATE, 0.82))
        return self.dedupe(findings)

    def anonymize(
        self,
        text: str,
        findings: list[Finding] | None = None,
        mode: AnonymizationMode = "standard",
    ) -> str:
        findings = findings if findings is not None else self.analyze(text, mode)
        chunks: list[str] = []
        cursor = 0

        for finding in sorted(findings, key=lambda item: item.start):
            if finding.start < cursor:
                continue
            chunks.append(text[cursor : finding.start])
            chunks.append(self._replacement(text[finding.start : finding.end], finding.entity_type, mode))
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
        # Manual scan: the greedy candidate can overrun the real IBAN (or the next one),
        # so the span is cut to the official country length before resuming the search.
        findings: list[Finding] = []
        position = 0

        while True:
            match = self.IBAN.search(text, position)
            if match is None:
                break
            compact = self._compact_iban(match.group(0))
            expected_length = IBAN_LENGTHS.get(compact[:2])
            if expected_length and len(compact) >= expected_length and self._valid_iban(compact[:expected_length]):
                end = self._offset_after_alnum(text, match.start(), expected_length)
                findings.append(Finding("IBAN", match.start(), end, 0.97))
                position = end
            else:
                position = match.start() + 1

        return findings

    def _offset_after_alnum(self, text: str, start: int, count: int) -> int:
        seen = 0
        index = start
        while index < len(text) and seen < count:
            if not text[index].isspace() and text[index] != "-":
                seen += 1
            index += 1
        return index

    def _credit_card_findings(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for match in self.CREDIT_CARD.finditer(text):
            digits = re.sub(r"[ -]", "", match.group(0))
            if not 13 <= len(digits) <= 19:
                continue
            if not self._valid_luhn(digits):
                continue
            findings.append(Finding("CREDIT_CARD", match.start(), match.end(), 0.95))
        return findings

    def _postal_code_city_findings(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for match in self.POSTAL_CODE_CITY.finditer(text):
            first_word = match.group("city").split()[0]
            if (
                first_word in self.PERSON_STOPWORDS
                or first_word in self.MONTH_NAMES
                or first_word in self.POSTAL_CITY_STOPWORDS
            ):
                continue
            findings.append(Finding("ADDRESS", match.start(), match.end(), 0.8))
        return findings

    def _international_phone_findings(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for match in self.INTERNATIONAL_PHONE.finditer(text):
            digits = sum(1 for char in match.group(0) if char.isdigit())
            if 8 <= digits <= 15:
                findings.append(Finding("PHONE_NUMBER", match.start(), match.end(), 0.92))
        return findings

    def _lowercase_address_findings(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for match in self.ADDRESS_LOWERCASE.finditer(text):
            words = match.group("name").split()
            if any(word in self.ADDRESS_NAME_STOPWORDS for word in words):
                continue
            findings.append(Finding("ADDRESS", match.start(), match.end(), 0.78))
        return findings

    def _pec_email_findings(self, text: str) -> list[Finding]:
        findings = [
            Finding("PEC_ADDRESS", match.start("email"), match.end("email"), 0.98)
            for match in self.PEC_CONTEXT.finditer(text)
        ]
        findings.extend(
            Finding("PEC_ADDRESS", match.start(), match.end(), 0.97)
            for match in self.EMAIL.finditer(text)
            if self._looks_like_pec_domain(match.group(0))
        )
        return findings

    def _sdi_code_findings(self, text: str) -> list[Finding]:
        return [
            Finding("SDI_CODE", match.start("sdi"), match.end("sdi"), 0.9)
            for match in self.SDI_CODE.finditer(text)
            if self._valid_sdi_code(match.group("sdi"))
        ]

    def _health_card_findings(self, text: str) -> list[Finding]:
        return [
            Finding("HEALTH_CARD", match.start("card"), match.end("card"), 0.9)
            for match in self.HEALTH_CARD.finditer(text)
            if self._valid_health_card(match.group("card"))
        ]

    def _identity_document_findings(self, text: str) -> list[Finding]:
        return [
            Finding("IDENTITY_DOCUMENT", match.start("document"), match.end("document"), 0.92)
            for match in self.IDENTITY_DOCUMENT.finditer(text)
            if self._valid_contextual_code(match.group("document"))
        ]

    def _vehicle_plate_findings(self, text: str) -> list[Finding]:
        return [
            Finding("VEHICLE_PLATE", match.start("plate"), match.end("plate"), 0.91)
            for match in self.VEHICLE_PLATE.finditer(text)
            if self._valid_contextual_code(match.group("plate"))
        ]

    def _protocol_case_findings(self, text: str) -> list[Finding]:
        return [
            Finding("PROTOCOL_CASE_NUMBER", match.start("case"), match.end("case"), 0.88)
            for match in self.PROTOCOL_CASE_NUMBER.finditer(text)
            if self._valid_protocol_case_code(match.group("case"))
        ]

    def _organization_findings(self, text: str) -> list[Finding]:
        findings = self._regex_findings(text, "ORGANIZATION", self.COMPANY_SUFFIX, 0.9, trim_period=False)
        findings.extend(self._regex_findings(text, "ORGANIZATION", self.COMPANY_PREFIX, 0.88, trim_period=False))
        return [finding for finding in findings if self._looks_like_organization(text[finding.start : finding.end])]

    def _territorial_body_findings(self, text: str) -> list[Finding]:
        return self._regex_findings(text, "TERRITORIAL_BODY", self.TERRITORIAL_BODY, 0.88)

    def _person_findings(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for pattern in (self.PERSON, self.PERSON_TRAILING_CONTEXT):
            for match in pattern.finditer(text):
                start = match.start("name")
                end = self._trim_end(text, match.end("name"), trim_period=True)
                name = text[start:end].strip()
                if self._looks_like_person_name(name):
                    findings.append(Finding("PERSON", start, end, 0.84))
        return findings

    def _dictionary_person_findings(self, text: str) -> list[Finding]:
        """Rileva persone senza titoli né contesto forte tramite il dizionario di nomi.

        A differenza di PERSON/PERSON_TRAILING_CONTEXT (che richiedono un titolo o
        un indizio testuale immediatamente prima/dopo il nome), questo riconoscitore
        si basa solo sulla prima parola del candidato: se è un nome di battesimo
        italiano noto e l'intero candidato "sembra" un nome di persona, viene
        segnalato con uno score più basso (0.72) e source="name_dictionary".
        """
        findings: list[Finding] = []
        last_end = -1
        for token in self.CAPITAL_NAME_TOKEN.finditer(text):
            if token.start() < last_end:
                continue
            if not is_italian_first_name(token.group(0)):
                continue
            match = self.DICTIONARY_PERSON_FROM_NAME.match(text, token.start())
            if match is None:
                continue
            candidate = match.group(0)
            if not self._looks_like_person_name(candidate):
                continue
            preceding = text[max(0, match.start() - 16) : match.start()]
            if self.STREET_PRECEDING_GUARD.search(preceding):
                continue
            findings.append(
                Finding("PERSON", match.start(), match.end(), self.DICTIONARY_PERSON_SCORE, source="name_dictionary")
            )
            last_end = match.end()
        return findings

    def _looks_like_person_name(self, name: str) -> bool:
        words = name.split()
        if len(words) < 2 or any(word.strip(" .") in self.PERSON_STOPWORDS for word in words):
            return False
        return True

    def propagate_person_coreferences(self, text: str, findings: list[Finding]) -> list[Finding]:
        """Estende i PERSON con contesto forte alle altre occorrenze dello stesso nome o cognome."""
        person_findings = [finding for finding in findings if finding.entity_type == "PERSON"]
        if not person_findings:
            return findings

        existing_spans = [(finding.start, finding.end) for finding in findings]
        new_findings: list[Finding] = []
        seen_candidates: set[str] = set()

        for finding in person_findings:
            name = text[finding.start : finding.end].strip()
            words = name.split()
            if len(words) < 2:
                continue

            candidates = {name}
            surname = words[-1].strip(" .")
            if len(surname) >= 3 and surname[:1].isupper() and self._is_propagatable_surname(surname):
                candidates.add(surname)

            for candidate in candidates - seen_candidates:
                seen_candidates.add(candidate)
                for match in re.finditer(rf"\b{re.escape(candidate)}\b", text):
                    if self._overlaps_any(match.start(), match.end(), existing_spans):
                        continue
                    new_findings.append(
                        Finding("PERSON", match.start(), match.end(), self.COREFERENCE_SCORE, source="coreference")
                    )

        return self.dedupe(findings + new_findings) if new_findings else findings

    def _is_propagatable_surname(self, surname: str) -> bool:
        if surname in self.PERSON_STOPWORDS:
            return False
        normalized = re.sub(r"[.'’]", "", surname).lower()
        return normalized not in self.KEYWORD_VOCABULARY

    def _overlaps_any(self, start: int, end: int, spans: list[tuple[int, int]]) -> bool:
        return any(start < span_end and span_start < end for span_start, span_end in spans)

    def dedupe(self, findings: list[Finding]) -> list[Finding]:
        priority = {
            "CODICE_FISCALE": 7,
            "PARTITA_IVA": 7,
            "IBAN": 7,
            "PEC_ADDRESS": 8,
            "EMAIL_ADDRESS": 7,
            "CREDIT_CARD": 6,
            "PHONE_NUMBER": 7,
            "SDI_CODE": 7,
            "HEALTH_CARD": 7,
            "IDENTITY_DOCUMENT": 7,
            "VEHICLE_PLATE": 7,
            "PROTOCOL_CASE_NUMBER": 7,
            "ORGANIZATION": 6,
            "TERRITORIAL_BODY": 6,
            "PERSON": 5,
            "ADDRESS": 4,
            "DATE": 3,
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

    def _compact_iban(self, value: str) -> str:
        return re.sub(r"[\s-]", "", value).upper()

    def _valid_luhn(self, digits: str) -> bool:
        if not digits.isdigit():
            return False
        total = 0
        for index, char in enumerate(reversed(digits)):
            digit = int(char)
            if index % 2 == 1:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        return total % 10 == 0

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

    def _valid_contextual_code(self, value: str) -> bool:
        compact = re.sub(r"[\s.-]", "", value).upper()
        return 5 <= len(compact) <= 12 and any(char.isdigit() for char in compact)

    def _valid_sdi_code(self, value: str) -> bool:
        compact = value.upper()
        return len(compact) in {6, 7} and compact.isalnum()

    def _valid_health_card(self, value: str) -> bool:
        compact = re.sub(r"[\s.-]", "", value)
        return len(compact) == 20 and compact.isdigit()

    def _looks_like_pec_domain(self, value: str) -> bool:
        domain = value.rsplit("@", 1)[-1].lower()
        labels = domain.split(".")
        known_domains = {
            "arubapec.it",
            "legalmail.it",
            "messaggipec.it",
            "pecimprese.it",
            "postacertificata.gov.it",
            "registerpec.it",
            "sicurezzapostale.it",
        }
        return (
            domain in known_domains
            or domain.endswith(".legalmail.it")
            or domain.endswith(".postacertificata.gov.it")
            or "pec" in labels
        )

    def _valid_protocol_case_code(self, value: str) -> bool:
        normalized = re.sub(r"\s+", "", value.strip().upper())
        compact = re.sub(r"[./-]", "", normalized)
        if not 4 <= len(compact) <= 24:
            return False
        if not any(char.isdigit() for char in compact):
            return False
        if re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", normalized):
            return False
        if re.fullmatch(r"(?:19|20)\d{2}", compact):
            return False
        return True

    def _replacement(self, value: str, entity_type: str, mode: AnonymizationMode) -> str:
        if mode in {"maximum", "reversible"}:
            return entity_placeholder(entity_type)
        if entity_type in {"PERSON", "ORGANIZATION", "TERRITORIAL_BODY", "ADDRESS"}:
            return self._initials(value)
        return entity_placeholder(entity_type)

    def _initials(self, value: str) -> str:
        tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", value)
        initials = [f"{token[0]}." for token in tokens if token and not token.isdigit()]
        return " ".join(initials) if initials else "<ANONIMIZZATO>"
