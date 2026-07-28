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
    "CATASTO": "Documenti",
    "ADDRESS": "Luoghi",
    "LOCATION": "Luoghi",
    "POSTAL_CODE": "Luoghi",
    "DATE": "Date",
    "ORGANIZATION": "Enti",
    "TERRITORIAL_BODY": "Enti",
}

CATEGORY_COLORS: dict[str, str] = {
    "Persone": "#4FB8E7",
    "Contatti": "#4CC38A",
    "Finanziari": "#EE8866",
    "Documenti": "#E57373",
    "Luoghi": "#A78BFA",
    "Date": "#D9A13B",
    "Enti": "#8899AA",
    "Altro": "#8899AA",
}

# Entity types validated with a real checksum (Luhn, IBAN mod-97, codice fiscale
# check digit, ...). Shown with a "✓" marker in the findings panel.
CHECKSUM_TYPES: frozenset[str] = frozenset(
    {"IBAN", "CREDIT_CARD", "CODICE_FISCALE", "PARTITA_IVA", "HEALTH_CARD"}
)

# Every meaningful category has its own filter. The panel hides zero-count pills,
# so the review stays compact without collapsing places, dates, or institutions
# into an opaque "Altro" bucket.
FILTER_CATEGORIES: tuple[str, ...] = (
    "Tutti",
    "Persone",
    "Contatti",
    "Finanziari",
    "Documenti",
    "Luoghi",
    "Date",
    "Enti",
    "Altro",
)


def entity_category(entity_type: str) -> str:
    return ENTITY_CATEGORIES.get(entity_type, "Altro")


def entity_color(entity_type: str) -> str:
    return CATEGORY_COLORS.get(entity_category(entity_type), CATEGORY_COLORS["Altro"])


def filter_category(entity_type: str) -> str:
    """Category bucket used by the dynamic filter pills."""
    category = entity_category(entity_type)
    return category if category in FILTER_CATEGORIES else "Altro"
