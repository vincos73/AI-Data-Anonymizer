#!/usr/bin/env python3
"""Valuta il corpus sintetico e produce una baseline leggibile e JSON."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from privacy_guardian import __version__
from privacy_guardian.document_service import load_document
from privacy_guardian.privacy_engine import PrivacyEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = PROJECT_ROOT / "documenti_di_prova" / "corpus_multisettore"


def occurrences(text: str, value: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in re.finditer(re.escape(value), text, flags=re.IGNORECASE)]


def expected_value_status(text: str, findings: list[object], value: str, entity_type: str) -> str:
    """Valuta tutte le occorrenze senza confondere copertura e classificazione.

    Un valore ripetuto è protetto se ogni occorrenza è interamente coperta da un
    finding sensibile e almeno una è classificata col tipo atteso. La punteggiatura
    terminale innocua può restare fuori dallo span senza costituire una perdita.
    """
    spans = occurrences(text, value)
    if not spans:
        return "not_extracted"

    effective_spans = []
    for start, end in spans:
        while end > start and text[end - 1] in ".,;:":
            end -= 1
        effective_spans.append((start, end))

    fully_covered = [
        any(finding.start <= start and end <= finding.end for finding in findings)
        for start, end in effective_spans
    ]
    if not all(fully_covered):
        return "leaked"

    correctly_typed = any(
        finding.start <= start
        and end <= finding.end
        and finding.entity_type == entity_type
        for start, end in effective_spans
        for finding in findings
    )
    return "detected" if correctly_typed else "wrong_type_or_span"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Esce con codice 1 se trova perdite o falsi positivi sui controlli.")
    args = parser.parse_args()

    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    engine = PrivacyEngine()
    results: list[dict[str, object]] = []
    totals = Counter()

    for case in manifest["cases"]:
        loaded = load_document(CORPUS_DIR / case["file"])
        findings = engine.analyze(loaded.text, "maximum")
        anonymized = engine.anonymize(loaded.text, findings, "maximum")
        expected_results = []
        for expected in case["expected_remove"]:
            status = expected_value_status(
                loaded.text,
                findings,
                expected["value"],
                expected["entity_type"],
            )
            totals[status] += 1
            expected_results.append({**expected, "status": status})

        remain_results = []
        for value in case["must_remain"]:
            source_present = bool(occurrences(loaded.text, value))
            output_present = bool(occurrences(anonymized, value))
            status = "preserved" if source_present and output_present else "false_positive" if source_present else "not_extracted"
            totals[status] += 1
            remain_results.append({"value": value, "status": status})

        results.append({
            "id": case["id"],
            "sector": case["sector"],
            "file": case["file"],
            "ocr_pages": list(loaded.ocr_pages),
            "finding_count": len(findings),
            "expected_remove": expected_results,
            "must_remain": remain_results,
        })

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "omissis_version": __version__,
        "ner_active": engine.ner_active,
        "mode": "maximum",
        "summary": dict(totals),
        "cases": results,
    }
    removable_total = totals["detected"] + totals["wrong_type_or_span"] + totals["leaked"]
    control_total = totals["preserved"] + totals["false_positive"]
    removal_rate = (
        100.0 * (totals["detected"] + totals["wrong_type_or_span"]) / removable_total
        if removable_total else 0.0
    )
    preservation_rate = 100.0 * totals["preserved"] / control_total if control_total else 0.0
    output["metrics"] = {
        "removal_rate_percent": round(removal_rate, 2),
        "preservation_rate_percent": round(preservation_rate, 2),
    }
    stem = f"baseline_v{__version__.replace('.', '_')}"
    json_path = CORPUS_DIR / f"{stem}.json"
    md_path = CORPUS_DIR / f"{stem}.md"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    issue_rows = []
    for case in results:
        issues = [
            f"{item['status']}: {item['entity_type']} = {item['value']}"
            for item in case["expected_remove"]
            if item["status"] != "detected"
        ]
        issues.extend(
            f"{item['status']}: controllo = {item['value']}"
            for item in case["must_remain"]
            if item["status"] != "preserved"
        )
        if issues:
            issue_rows.append((case["id"], case["file"], "; ".join(issues)))

    lines = [
        f"# Baseline corpus multi-settore - OMISSIS v{__version__}",
        "",
        f"- Modalità: Massima protezione",
        f"- NER locale attivo: {'sì' if engine.ner_active else 'no'}",
        f"- Casi analizzati: {len(results)}",
        f"- Valori sensibili rilevati e rimossi: {totals['detected']}",
        f"- Valori presenti ma rimasti nell'output: {totals['leaked']}",
        f"- Tipo o intervallo non conforme: {totals['wrong_type_or_span']}",
        f"- Valori non estratti dal documento/OCR: {totals['not_extracted']}",
        f"- Controlli innocui preservati: {totals['preserved']}",
        f"- Possibili falsi positivi sui controlli: {totals['false_positive']}",
        f"- Tasso di rimozione verificabile: {removal_rate:.1f}%",
        f"- Tasso di preservazione dei controlli: {preservation_rate:.1f}%",
        "",
        "## Anomalie da esaminare",
        "",
    ]
    if issue_rows:
        for case_id, filename, issues in issue_rows:
            lines.append(f"- **{case_id}** (`{filename}`): {issues}")
    else:
        lines.append("Nessuna anomalia rispetto alle attese dichiarate nel manifest.")
    lines.extend([
        "",
        "## Lettura corretta dei risultati",
        "",
        "`not_extracted` indica un problema di estrazione o OCR, non necessariamente del riconoscitore. `wrong_type_or_span` richiede un controllo manuale: il valore potrebbe essere stato coperto da un finding più ampio. La baseline non sostituisce la verifica visiva dei documenti esportati.",
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False, sort_keys=True))
    print(md_path)

    failures = totals["leaked"] + totals["wrong_type_or_span"] + totals["false_positive"]
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
