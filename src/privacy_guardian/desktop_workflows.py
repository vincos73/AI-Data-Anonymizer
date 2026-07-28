from __future__ import annotations

from dataclasses import dataclass

from privacy_guardian.desktop_jobs import JobContext
from privacy_guardian.document_service import AnonymizedDocument, LoadedDocument, anonymize_loaded_document
from privacy_guardian.models import AnonymizationMode, Finding
from privacy_guardian.privacy_engine import PrivacyEngine
from privacy_guardian.reversible import ReversibleMapEntry


@dataclass(frozen=True)
class AnalysisOutcome:
    source_text: str
    mode: AnonymizationMode
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class AnonymizationRequest:
    source_text: str
    mode: AnonymizationMode
    loaded_document: LoadedDocument | None
    reversible_entries: tuple[ReversibleMapEntry, ...]
    findings: tuple[Finding, ...] | None
    findings_were_reviewed: bool
    selected_total: int
    selected_included: int
    excluded_values: frozenset[tuple[str, str]] | None = None
    extra_values: frozenset[tuple[str, str]] | None = None


@dataclass(frozen=True)
class AnonymizationOutcome:
    mode: AnonymizationMode
    output_text: str
    findings: tuple[Finding, ...]
    mapping: tuple[ReversibleMapEntry, ...]
    total_findings: int
    included_findings: int
    output_data: bytes
    document: AnonymizedDocument | None = None


def analyze_text(engine: PrivacyEngine, source_text: str, mode: AnonymizationMode, context: JobContext) -> AnalysisOutcome:
    context.progress(10, "Preparazione dell'analisi")
    context.progress(25, "Riconoscimento dei dati sensibili")
    findings = tuple(engine.analyze(source_text, mode))
    context.progress(100, f"Analisi completata: {len(findings)} elementi")
    return AnalysisOutcome(source_text=source_text, mode=mode, findings=findings)


def anonymize(engine: PrivacyEngine, request: AnonymizationRequest, context: JobContext) -> AnonymizationOutcome:
    context.progress(5, "Preparazione dell'anonimizzazione")
    findings = list(request.findings) if request.findings is not None else engine.analyze(
        request.source_text,
        request.mode,
    )
    context.check_cancelled()

    if request.loaded_document is not None:
        document = anonymize_loaded_document(
            request.loaded_document,
            engine,
            request.mode,
            reversible_entries=request.reversible_entries,
            findings=findings if request.findings is not None else None,
            excluded_values=request.excluded_values,
            extra_values=request.extra_values,
            progress_callback=context.progress,
            cancel_check=context.check_cancelled,
        )
        total = request.selected_total if request.findings_were_reviewed else len(document.findings)
        included = request.selected_included if request.findings_were_reviewed else total
        return AnonymizationOutcome(
            mode=request.mode,
            output_text=document.text,
            findings=tuple(document.findings),
            mapping=document.reversible_mapping,
            total_findings=total,
            included_findings=included,
            output_data=document.data,
            document=document,
        )

    context.progress(55, "Applicazione delle sostituzioni")
    if request.mode == "reversible":
        reversible = engine.anonymize_reversible(
            request.source_text,
            findings,
            entries=request.reversible_entries,
        )
        output_text = reversible.text
        mapping = reversible.mapping
    else:
        output_text = engine.anonymize(request.source_text, findings, request.mode)
        mapping = ()
    context.progress(100, "Testo anonimizzato")
    return AnonymizationOutcome(
        mode=request.mode,
        output_text=output_text,
        findings=tuple(findings),
        mapping=mapping,
        total_findings=request.selected_total if request.findings_were_reviewed else len(findings),
        included_findings=request.selected_included if request.findings_were_reviewed else len(findings),
        output_data=output_text.encode("utf-8"),
    )
