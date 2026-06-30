from __future__ import annotations

from collections import Counter

from privacy_guardian.models import AnonymizationMode, Finding


ENTITY_LABELS = {
    "ADDRESS": ("indirizzo", "indirizzi"),
    "CODICE_FISCALE": ("codice fiscale", "codici fiscali"),
    "DATE": ("data", "date"),
    "EMAIL_ADDRESS": ("email", "email"),
    "IBAN": ("IBAN", "IBAN"),
    "ORGANIZATION": ("organizzazione", "organizzazioni"),
    "PARTITA_IVA": ("partita IVA", "partite IVA"),
    "PERSON": ("persona", "persone"),
    "PHONE_NUMBER": ("telefono", "telefoni"),
    "TERRITORIAL_BODY": ("ente territoriale", "enti territoriali"),
}
MODE_LABELS = {
    "standard": "Standard",
    "maximum": "Massima protezione",
}
MODE_NOTES = {
    "standard": "Standard conserva iniziali e date: per testo da condividere con chatbot valuta Massima protezione.",
    "maximum": "Massima protezione usa segnaposto completi e redige anche date comuni riconosciute.",
}
REVIEW_NOTE = "Rileggi sempre il risultato prima di condividerlo."


def mode_label(mode: AnonymizationMode) -> str:
    return MODE_LABELS[mode]


def mode_note(mode: AnonymizationMode) -> str:
    return MODE_NOTES[mode]


def finding_counts(findings: list[Finding]) -> dict[str, int]:
    return dict(Counter(finding.entity_type for finding in findings))


def finding_types_summary(findings: list[Finding]) -> str:
    counts = finding_counts(findings)
    if not counts:
        return "nessun dato riconosciuto"

    parts = [
        f"{count} {entity_label(entity_type, count)}"
        for entity_type, count in sorted(counts.items(), key=lambda item: entity_label(item[0], 2))
    ]
    return ", ".join(parts)


def report_text(findings: list[Finding], mode: AnonymizationMode) -> str:
    total = len(findings)
    item_label = "dato riconosciuto" if total == 1 else "dati riconosciuti"
    return (
        f"Modalità {mode_label(mode)}: {total} {item_label} "
        f"({finding_types_summary(findings)}). {mode_note(mode)} {REVIEW_NOTE}"
    )


def report_payload(findings: list[Finding], mode: AnonymizationMode) -> dict[str, object]:
    return {
        "mode": mode,
        "mode_label": mode_label(mode),
        "mode_note": mode_note(mode),
        "review_note": REVIEW_NOTE,
        "total": len(findings),
        "counts": finding_counts(findings),
        "summary": report_text(findings, mode),
    }


def entity_label(entity_type: str, count: int = 1) -> str:
    labels = ENTITY_LABELS.get(entity_type)
    if labels is None:
        return entity_type
    singular, plural = labels
    return singular if count == 1 else plural
