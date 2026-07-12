"""Category grouping and color tokens for entity types, used by the desktop findings panel.

Kept separate from reporting.py (which is shared with the web app) so the desktop-only
UI grouping/coloring concerns don't leak into the web app's payloads.
"""

from __future__ import annotations


ENTITY_CATEGORIES: dict[str, str] = {
    "PERSON": "Persone",
    "EMAIL_ADDRESS": "Contatti",
    "PEC_ADDRESS": "Contatti",
    "PHONE_NUMBER": "Contatti",
    "IBAN": "Finanziari",
    "CREDIT_CARD": "Finanziari",
    "SDI_CODE": "Finanziari",
    "CODICE_FISCALE": "Documenti",
    "PARTITA_IVA": "Documenti",
    "IDENTITY_DOCUMENT": "Documenti",
    "HEALTH_CARD": "Documenti",
    "VEHICLE_PLATE": "Documenti",
    "PROTOCOL_CASE_NUMBER": "Documenti",
    "ADDRESS": "Indirizzi",
    "DATE": "Date",
    "ORGANIZATION": "Altro",
    "TERRITORIAL_BODY": "Altro",
}

CATEGORY_COLORS: dict[str, str] = {
    "Persone": "#4FB8E7",
    "Contatti": "#4CC38A",
    "Finanziari": "#EE8866",
    "Documenti": "#E57373",
    "Indirizzi": "#A78BFA",
    "Date": "#D9A13B",
    "Altro": "#8899AA",
}

# Entity types validated with a real checksum (Luhn, IBAN mod-97, codice fiscale
# check digit, ...). Shown with a "✓" marker in the findings panel.
CHECKSUM_TYPES: frozenset[str] = frozenset(
    {"IBAN", "CREDIT_CARD", "CODICE_FISCALE", "PARTITA_IVA", "HEALTH_CARD"}
)

# The findings panel's filter pills only expose these six buckets. Categories not
# listed here (Indirizzi, Date) fall back to "Altro" for filtering purposes, but
# keep their own CATEGORY_COLORS for badges/highlights.
FILTER_CATEGORIES: tuple[str, ...] = ("Tutti", "Persone", "Contatti", "Finanziari", "Documenti", "Altro")


def entity_category(entity_type: str) -> str:
    return ENTITY_CATEGORIES.get(entity_type, "Altro")


def entity_color(entity_type: str) -> str:
    return CATEGORY_COLORS.get(entity_category(entity_type), CATEGORY_COLORS["Altro"])


def filter_category(entity_type: str) -> str:
    """Category bucket used by the filter pills (Indirizzi/Date collapse into Altro)."""
    category = entity_category(entity_type)
    return category if category in FILTER_CATEGORIES else "Altro"
