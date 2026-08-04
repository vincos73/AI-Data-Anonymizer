from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import unicodedata

from privacy_guardian.models import Finding


_LOCATIONS_FILE = Path(__file__).parent / "assets" / "localita_italiane_istat.txt"
_LOCATION_TOKEN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:['’/-][A-Za-zÀ-ÖØ-öø-ÿ]+)*")
_LOCATION_TEXT = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ'’/\-\s]+")
_ADDRESS_MARKER = re.compile(
    r"\b(?:via|v\.|viale|v\.le|piazza|p\.zza|piazzale|corso|c\.so|vicolo|largo|"
    r"strada|contrada|frazione)\b",
    re.IGNORECASE,
)
_INSTITUTION_MARKER = re.compile(
    r"\b(?:universit[aà]|dipartimento)\b",
    re.IGNORECASE,
)
_NON_LOCATION_MARKER = re.compile(
    r"\b(?:corpo|relazione|servizio|personale|ispettori|ufficio|comando)\b",
    re.IGNORECASE,
)
_PERSON_TITLE_MARKER = re.compile(
    r"\b(?:sig\.?\s*ra\.?|sig\.?|signora?|dott\.?\s*ssa\.?|dott\.?|avv\.?|ing\.?|"
    r"geom\.?|rag\.?|prof\.?\s*ssa\.?|prof\.?|notaio|notaia)\b",
    re.IGNORECASE,
)
_PERSON_TITLE_CONTEXT = re.compile(
    r"\b(?:sig\.?\s*ra\.?|sig\.?|signora?|dott\.?\s*ssa\.?|dott\.?|avv\.?|ing\.?|"
    r"geom\.?|rag\.?|prof\.?\s*ssa\.?|prof\.?|notaio|notaia)\s*$",
    re.IGNORECASE,
)
_TRIE_END = ""
_FIELD_DELIMITERS = "\n\r\t,;|"
_LOCATION_CONTEXT = (
    re.compile(r"\b(?:a|ad|in|da|dal|dalla|dai|dalle|presso|verso)\s+$", re.IGNORECASE),
    # Se spaCy ingloba il nome dell'ufficio giudiziario, il relativo finding NER
    # viene scartato; questo contesto permette comunque al dizionario ISTAT di
    # conservare il solo toponimo finale (Potenza/Firenze negli esempi reali).
    re.compile(
        r"\bcorte(?:\s+di)?\s+appello(?:\s+di)?\s+$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:nato|nata|residente|domiciliato|domiciliata|vive|abitante|sede|luogo|"
        r"localit[aà]|citt[aà]|comune|provincia|regione|territorio)"
        r"(?:\s+(?:a|ad|in|di|nel|nella))?\s+$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:comuni?|localit[aà]|frazioni?|zone|territori)\b"
        r"(?:[ \t]+(?:vigilat[ioe]|interessat[ioe]|coinvolt[ioe]|servit[ioe]))?"
        r"[ \t]*[:\-–—]?[ \t]*$",
        re.IGNORECASE,
    ),
)
_AMBIGUOUS_LOCATION_FOLLOWING = {
    "potenza": re.compile(r"^\s+(?:di|del|dello|della|dei|degli|delle)\b", re.IGNORECASE),
}
_NER_LOCATION_EXACT_REJECTIONS = frozenset(
    {
        "collegio",
        "euro",
        "parte venditrice",
        "provincia",
        "province",
    }
)
_LEGAL_NER_FALSE_POSITIVE = re.compile(
    r"\b(?:"
    r"corte(?:\s+di)?\s+appello|"
    r"giudice\s+(?:di\s+merito|delle\s+leggi)|"
    r"comuni?\s+alle\s+province|"
    r"difetto\s+di\s+motivazione|"
    r"istituto\s+professionale|"
    r"mancata\s+pronuncia|"
    r"spetta\s+alle\s+regioni|"
    r"autorità\s+giudiziaria"
    r")\b"
)
_AMBIGUOUS_NON_LOCATION_TERMS = frozenset({"comparsa", "note"})
_LOCATION_LABELS = frozenset({"localita", "località", "frazione"})
_LOCATION_NAME_WORD = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*"
_LOCATION_NAME = (
    rf"{_LOCATION_NAME_WORD}"
    rf"(?:[ \t]+(?:(?:di|del|della|dei|degli|delle|d['’])"
    rf"[ \t]+)?{_LOCATION_NAME_WORD}){{0,3}}"
)
_LABELED_LOCALITY_LIST = re.compile(
    rf"\b(?:localit[aà]|frazione)[ \t]+"
    rf"(?P<names>{_LOCATION_NAME}"
    rf"(?:(?:[ \t]*[,;/][ \t]*|[ \t]+e[ \t]+){_LOCATION_NAME}){{0,5}})",
    re.IGNORECASE,
)
_LABELED_MUNICIPALITY_LIST = re.compile(
    rf"\bcomuni?"
    rf"(?:[ \t]+(?:vigilat[ioe]|interessat[ioe]|coinvolt[ioe]|servit[ioe]))?"
    rf"[ \t]*:[ \t]*"
    rf"(?P<names>{_LOCATION_NAME}"
    rf"(?:(?:[ \t]*[,;/][ \t]*|[ \t]+e[ \t]+){_LOCATION_NAME}){{0,5}})",
    re.IGNORECASE,
)
_LOCATION_LIST_SEPARATOR = re.compile(r"[ \t]*[,;/][ \t]*|[ \t]+e[ \t]+", re.IGNORECASE)


@dataclass(frozen=True)
class ItalianLocationIndex:
    municipalities: frozenset[str]
    regions: frozenset[str]
    territorial_areas: frozenset[str]

    @property
    def all_names(self) -> frozenset[str]:
        return self.municipalities | self.regions | self.territorial_areas

    def contains(self, value: str) -> bool:
        return normalize_location_name(value) in self.all_names

    def is_region(self, value: str) -> bool:
        return normalize_location_name(value) in self.regions


@dataclass(frozen=True)
class KnownLocationSpan:
    start: int
    end: int
    value: str


def normalize_location_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("’", "'")
    normalized = re.sub(r"[‐‑–—]", "-", normalized)
    return " ".join(token.casefold() for token in _LOCATION_TOKEN.findall(normalized))


def is_legal_ner_false_positive(value: str) -> bool:
    """Recognize legal phrases spaCy may mislabel as either a place or a person."""
    return _LEGAL_NER_FALSE_POSITIVE.search(normalize_location_name(value)) is not None


@lru_cache(maxsize=1)
def load_italian_locations() -> ItalianLocationIndex:
    grouped: dict[str, set[str]] = {"comune": set(), "regione": set(), "uts": set()}
    try:
        lines = _LOCATIONS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []

    for line in lines:
        if not line or line.startswith("#") or "\t" not in line:
            continue
        kind, value = line.split("\t", 1)
        normalized = normalize_location_name(value)
        if kind in grouped and normalized:
            grouped[kind].add(normalized)

    return ItalianLocationIndex(
        municipalities=frozenset(grouped["comune"]),
        regions=frozenset(grouped["regione"]),
        territorial_areas=frozenset(grouped["uts"]),
    )


def _is_ambiguous_non_location_candidate(value: str) -> bool:
    """Reject legal-document words unless the official location index knows them."""
    normalized = normalize_location_name(value)
    parts = normalized.split(maxsplit=1)
    candidate = (
        parts[1]
        if len(parts) == 2 and parts[0] in _LOCATION_LABELS
        else normalized
    )
    return (
        candidate in _AMBIGUOUS_NON_LOCATION_TERMS
        and not load_italian_locations().contains(candidate)
    )


@lru_cache(maxsize=1)
def _location_trie() -> dict[str, dict]:
    trie: dict[str, dict] = {}
    for name in load_italian_locations().all_names:
        tokens = name.split()
        if not tokens:
            continue
        node = trie
        for token in tokens:
            node = node.setdefault(token, {})
        node[_TRIE_END] = {}
    return trie


def iter_known_location_spans(text: str) -> list[KnownLocationSpan]:
    tokens = [
        (match.start(), match.end(), normalize_location_name(match.group(0)))
        for match in _LOCATION_TOKEN.finditer(text)
    ]
    trie = _location_trie()
    spans: list[KnownLocationSpan] = []
    index = 0

    while index < len(tokens):
        node = trie
        best_end: int | None = None
        best_token_index: int | None = None
        cursor = index
        while cursor < len(tokens):
            if cursor > index and text[tokens[cursor - 1][1] : tokens[cursor][0]].strip():
                break
            token = tokens[cursor][2]
            child = node.get(token)
            if child is None:
                break
            node = child
            if _TRIE_END in node:
                best_end = tokens[cursor][1]
                best_token_index = cursor
            cursor += 1

        if best_end is None or best_token_index is None:
            index += 1
            continue

        start = tokens[index][0]
        spans.append(KnownLocationSpan(start, best_end, text[start:best_end]))
        index = best_token_index + 1

    return spans


def looks_like_location_text(value: str) -> bool:
    stripped = value.strip()
    return (
        bool(stripped)
        and not stripped.islower()
        and _LOCATION_TEXT.fullmatch(stripped) is not None
        and bool(_LOCATION_TOKEN.search(stripped))
    )


def contains_address_marker(value: str) -> bool:
    return _ADDRESS_MARKER.search(value) is not None


def has_location_context(text: str, start: int) -> bool:
    prefix = text[max(0, start - 100) : start]
    return any(pattern.search(prefix) for pattern in _LOCATION_CONTEXT)


def has_person_title_context(text: str, start: int) -> bool:
    prefix = text[max(0, start - 40) : start]
    return _PERSON_TITLE_CONTEXT.search(prefix) is not None


def is_standalone_location_field(text: str, start: int, end: int) -> bool:
    left = max((text.rfind(delimiter, 0, start) for delimiter in _FIELD_DELIMITERS), default=-1)
    right_candidates = [
        position
        for delimiter in _FIELD_DELIMITERS
        if (position := text.find(delimiter, end)) >= 0
    ]
    right = min(right_candidates, default=len(text))
    field = text[left + 1 : right].strip(" \t\"'()[]{}.:")
    return normalize_location_name(field) == normalize_location_name(text[start:end])


def should_accept_ner_location(text: str, start: int, end: int, value: str) -> bool:
    normalized = normalize_location_name(value)
    if (
        not looks_like_location_text(value)
        or contains_address_marker(value)
        or _INSTITUTION_MARKER.search(value)
        or _NON_LOCATION_MARKER.search(value)
        or _PERSON_TITLE_MARKER.search(value)
        or has_person_title_context(text, start)
        or normalized in _NER_LOCATION_EXACT_REJECTIONS
        or is_legal_ner_false_positive(value)
        or _is_ambiguous_non_location_candidate(value)
        or re.search(r"\n[ \t]*\n", value)
    ):
        return False

    context = has_location_context(text, start)
    standalone = is_standalone_location_field(text, start, end)
    ambiguity = _AMBIGUOUS_LOCATION_FOLLOWING.get(normalized)
    if ambiguity and ambiguity.search(text[end:]) and not context and not standalone:
        return False

    locations = load_italian_locations()
    if normalized in locations.all_names:
        return True
    return context or len(normalized.split()) >= 2


def dictionary_location_findings(text: str) -> list[Finding]:
    locations = load_italian_locations()
    findings: list[Finding] = []
    for span in iter_known_location_spans(text):
        if not looks_like_location_text(span.value):
            continue
        if not (
            locations.is_region(span.value)
            or has_location_context(text, span.start)
            or is_standalone_location_field(text, span.start, span.end)
        ):
            continue
        score = 0.9 if locations.is_region(span.value) else 0.82
        findings.append(
            Finding("LOCATION", span.start, span.end, score, source="location_dictionary")
        )
    return findings


def labeled_locality_findings(text: str) -> list[Finding]:
    """Detect municipalities and hamlets introduced by an explicit list label."""
    findings: list[Finding] = []
    for pattern in (_LABELED_LOCALITY_LIST, _LABELED_MUNICIPALITY_LIST):
        for match in pattern.finditer(text):
            names_start = match.start("names")
            names = match.group("names")
            cursor = 0
            for part in _LOCATION_LIST_SEPARATOR.split(names):
                value = part.strip(" \t.;:")
                if not value:
                    continue
                if _is_ambiguous_non_location_candidate(value):
                    continue
                relative_start = names.find(value, cursor)
                if relative_start < 0:
                    continue
                start = names_start + relative_start
                end = start + len(value)
                findings.append(Finding("LOCATION", start, end, 0.86, source="italian_rules"))
                cursor = relative_start + len(value)
    return findings
