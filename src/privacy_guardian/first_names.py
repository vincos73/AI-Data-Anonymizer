from __future__ import annotations

import string
from functools import lru_cache
from pathlib import Path

# Nessuna dipendenza da Qt: questo modulo deve poter essere importato sia dall'app
# desktop sia dal motore di anonimizzazione "puro" (document_service, engine, web).
# Path(__file__).parent funziona sia da sorgente sia in una build PyInstaller quando
# gli asset del pacchetto sono inclusi con --collect-data privacy_guardian (vedi
# scripts/build_macos_app.sh e scripts/build_windows_app.ps1), perché in quel caso
# PyInstaller ricrea la stessa struttura di cartelle del pacchetto sotto _MEIPASS.
_NAMES_FILE = Path(__file__).parent / "assets" / "nomi_italiani.txt"

_STRIP_CHARS = string.punctuation + " \t\n\r"


@lru_cache(maxsize=1)
def load_italian_first_names() -> frozenset[str]:
    """Carica il dizionario locale di nomi propri italiani (un nome per riga, minuscolo).

    Il file è incluso nel pacchetto (vedi pyproject.toml, package-data
    "assets/*.txt") e non richiede alcuna dipendenza esterna o rete: funziona
    identico nell'app desktop, nella web app locale e nelle build pacchettizzate.
    """
    try:
        raw = _NAMES_FILE.read_text(encoding="utf-8")
    except OSError:
        return frozenset()

    names = {line.strip().lower() for line in raw.splitlines() if line.strip()}
    return frozenset(names)


def is_italian_first_name(word: str) -> bool:
    """Verifica se `word` è un nome di battesimo italiano noto (case-insensitive)."""
    normalized = word.strip(_STRIP_CHARS).lower()
    if not normalized:
        return False
    return normalized in load_italian_first_names()
