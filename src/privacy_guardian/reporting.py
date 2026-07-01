from __future__ import annotations

from collections import Counter

from privacy_guardian.models import AnonymizationMode, Finding


ENTITY_LABELS = {
    "ADDRESS": ("indirizzo", "indirizzi"),
    "CODICE_FISCALE": ("codice fiscale", "codici fiscali"),
    "DATE": ("data", "date"),
    "EMAIL_ADDRESS": ("email", "email"),
    "IBAN": ("IBAN", "IBAN"),
    "IDENTITY_DOCUMENT": ("documento d'identità", "documenti d'identità"),
    "ORGANIZATION": ("organizzazione", "organizzazioni"),
    "PARTITA_IVA": ("partita IVA", "partite IVA"),
    "PERSON": ("persona", "persone"),
    "PHONE_NUMBER": ("telefono", "telefoni"),
    "TERRITORIAL_BODY": ("ente territoriale", "enti territoriali"),
    "VEHICLE_PLATE": ("targa veicolo", "targhe veicolo"),
}
MODE_LABELS = {
    "standard": "Standard",
    "maximum": "Massima protezione",
}
MODE_NOTES = {
    "standard": "Standard conserva iniziali e date: per testo da condividere con chatbot valuta Massima protezione.",
    "maximum": "Massima protezione usa segnaposto completi e redige anche date comuni riconosciute.",
}
SOURCE_LABELS = {
    "italian_rules": "Regole italiane locali",
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
        "checklist": review_checklist(findings, mode),
        "total": len(findings),
        "counts": finding_counts(findings),
        "summary": report_text(findings, mode),
    }


def review_checklist(findings: list[Finding], mode: AnonymizationMode) -> list[str]:
    items = []
    if mode == "maximum":
        items.append("Massima protezione è consigliata prima di condividere testi con chatbot o servizi esterni.")
    else:
        items.append("Standard lascia visibili iniziali e date: passa a Massima protezione per testi da condividere con chatbot.")

    if findings:
        items.append("Controlla se nel testo restano nomi, luoghi o dettagli identificativi non evidenziati.")
    else:
        items.append("Nessun dato riconosciuto non significa anonimizzazione garantita: rileggi il testo con attenzione.")

    items.append(REVIEW_NOTE)
    return items


def entity_label(entity_type: str, count: int = 1) -> str:
    labels = ENTITY_LABELS.get(entity_type)
    if labels is None:
        return entity_type
    singular, plural = labels
    return singular if count == 1 else plural


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)
