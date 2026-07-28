#!/usr/bin/env python3
"""Confronta i modelli NER italiani sul comportamento end-to-end di OMISSIS.

Il benchmark usa soltanto dati sintetici. Il profilo ``core`` copre i casi
italiani e i falsi positivi già emersi durante lo sviluppo; il profilo
``challenge`` misura nomi internazionali più difficili senza bloccare la build.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from time import perf_counter
from unittest.mock import patch

import spacy

from privacy_guardian.models import Finding
from privacy_guardian.ner_recognizer import NerPersonRecognizer
from privacy_guardian.privacy_engine import PrivacyEngine


Entity = tuple[str, str]


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    profile: str
    text: str
    required: tuple[Entity, ...] = ()
    forbidden: tuple[Entity, ...] = ()


CASES = (
    BenchmarkCase(
        name="nominativi_esteri_senza_contesto",
        profile="core",
        text=(
            "Wolfgang Keller ha incontrato Elin Andersson. "
            "Amina El Fassi ha scritto a Jean-Baptiste Moreau."
        ),
        required=(
            ("PERSON", "Wolfgang Keller"),
            ("PERSON", "Elin Andersson"),
            ("PERSON", "Amina El Fassi"),
            ("PERSON", "Jean-Baptiste Moreau"),
        ),
    ),
    BenchmarkCase(
        name="elenco_personale_cognome_nome",
        profile="core",
        text=(
            "Personale incaricato:\n"
            "Cresci Nicola\n"
            "LABANCA Giuseppe\n"
            "CRISTALDI Giovanni\n"
            "IMPERATO Daniele"
        ),
        required=(
            ("PERSON", "Cresci Nicola"),
            ("PERSON", "LABANCA Giuseppe"),
            ("PERSON", "CRISTALDI Giovanni"),
            ("PERSON", "IMPERATO Daniele"),
        ),
    ),
    BenchmarkCase(
        name="localita_italiane",
        profile="core",
        text=(
            "Comuni vigilati: Rotondella e Parrutta.\n"
            "La sede operativa è a Venosa, in Basilicata. "
            "L'ufficio provinciale è a Potenza."
        ),
        required=(
            ("LOCATION", "Rotondella"),
            ("LOCATION", "Parrutta"),
            ("LOCATION", "Venosa"),
            ("LOCATION", "Basilicata"),
            ("LOCATION", "Potenza"),
        ),
    ),
    BenchmarkCase(
        name="localita_estere",
        profile="core",
        text=(
            "La sede europea è a Parigi; gli incontri si tengono a New York "
            "e a San Sebastián."
        ),
        required=(
            ("LOCATION", "Parigi"),
            ("LOCATION", "New York"),
            ("LOCATION", "San Sebastián"),
        ),
    ),
    BenchmarkCase(
        name="societa_ocr",
        profile="core",
        text="La ditta di trasporto GEO -S. S. r. l esegue il servizio.",
        required=(("ORGANIZATION", "GEO -S. S. r. l"),),
    ),
    BenchmarkCase(
        name="enti_con_contesto",
        profile="core",
        text=(
            "Provincia di Potenza e Università degli Studi della Basilicata. "
            "Dipartimento di Ingegneria."
        ),
        required=(
            ("TERRITORIAL_BODY", "Provincia di Potenza"),
            ("ORGANIZATION", "Università degli Studi della Basilicata"),
            ("ORGANIZATION", "Dipartimento di Ingegneria"),
        ),
        forbidden=(
            ("LOCATION", "Università degli Studi della Basilicata"),
            ("LOCATION", "Dipartimento di Ingegneria"),
        ),
    ),
    BenchmarkCase(
        name="falsi_positivi_pdf",
        profile="core",
        text=(
            "La potenza del motore è elevata. Gli Ispettori leggono la relazione. "
            "Il residente abita in Via Appia 12."
        ),
        required=(("ADDRESS", "Via Appia 12"),),
        forbidden=(
            ("LOCATION", "potenza"),
            ("LOCATION", "Ispettori"),
            ("LOCATION", "Via Appia"),
        ),
    ),
    BenchmarkCase(
        name="email_csv",
        profile="core",
        text="Wolfgang Keller,wolfgang@example.com",
        required=(("EMAIL_ADDRESS", "wolfgang@example.com"),),
        forbidden=(("PERSON", "Wolfgang Keller,wolfgang@example.com"),),
    ),
    BenchmarkCase(
        name="riferimenti_catastali",
        profile="core",
        text="Catasto fabbricati: foglio 12, particella 345, subalterno 6.",
        required=(
            ("CATASTO", "12"),
            ("CATASTO", "345"),
            ("CATASTO", "6"),
        ),
    ),
    BenchmarkCase(
        name="nomi_internazionali_con_diacritici",
        profile="challenge",
        text=(
            "Alla riunione partecipano José María Álvarez, Siobhán O’Connor "
            "e Łukasz Kowalski."
        ),
        required=(
            ("PERSON", "José María Álvarez"),
            ("PERSON", "Siobhán O’Connor"),
            ("PERSON", "Łukasz Kowalski"),
        ),
    ),
    BenchmarkCase(
        name="nomi_internazionali_multicomponente",
        profile="challenge",
        text=(
            "Il rapporto è firmato da Mei Lin Chen e Fatima Zahra El Idrissi. "
            "Hanno risposto Nils Østergård e Jean-Luc Picard."
        ),
        required=(
            ("PERSON", "Mei Lin Chen"),
            ("PERSON", "Fatima Zahra El Idrissi"),
            ("PERSON", "Nils Østergård"),
            ("PERSON", "Jean-Luc Picard"),
        ),
        forbidden=(
            ("LOCATION", "Mei Lin Chen"),
            ("LOCATION", "Fatima Zahra El Idrissi"),
        ),
    ),
)


@dataclass(frozen=True)
class ModelResult:
    model: str
    load_seconds: float
    analyze_seconds: float
    required_hits: dict[str, int]
    required_total: dict[str, int]
    forbidden_hits: dict[str, int]
    details: tuple[str, ...]


def _engine_for_model(model_name: str) -> tuple[PrivacyEngine, float]:
    started = perf_counter()
    nlp = spacy.load(model_name)
    load_seconds = perf_counter() - started
    with patch(
        "privacy_guardian.privacy_engine.NerPersonRecognizer.create_if_available",
        return_value=None,
    ):
        engine = PrivacyEngine()
    engine._ner = NerPersonRecognizer(nlp)
    engine.ner_active = True
    return engine, load_seconds


def _entities(text: str, findings: list[Finding]) -> set[Entity]:
    return {
        (finding.entity_type, text[finding.start : finding.end])
        for finding in findings
    }


def evaluate(model_name: str, repeats: int) -> ModelResult:
    engine, load_seconds = _engine_for_model(model_name)
    required_hits = {"core": 0, "challenge": 0}
    required_total = {"core": 0, "challenge": 0}
    forbidden_hits = {"core": 0, "challenge": 0}
    details: list[str] = []

    started = perf_counter()
    for _ in range(repeats):
        for case in CASES:
            actual = _entities(case.text, engine.analyze(case.text, "maximum"))
            if _ == 0:
                missing = [entity for entity in case.required if entity not in actual]
                forbidden = [entity for entity in case.forbidden if entity in actual]
                required_total[case.profile] += len(case.required)
                required_hits[case.profile] += len(case.required) - len(missing)
                forbidden_hits[case.profile] += len(forbidden)
                if missing or forbidden:
                    details.append(
                        f"{case.profile}/{case.name}: "
                        f"mancanti={missing or '-'} vietati={forbidden or '-'}"
                    )
    analyze_seconds = (perf_counter() - started) / repeats

    return ModelResult(
        model=model_name,
        load_seconds=load_seconds,
        analyze_seconds=analyze_seconds,
        required_hits=required_hits,
        required_total=required_total,
        forbidden_hits=forbidden_hits,
        details=tuple(details),
    )


def print_result(result: ModelResult) -> None:
    print(f"\n{result.model}")
    print(
        f"  caricamento: {result.load_seconds:.3f}s · "
        f"analisi set: {result.analyze_seconds:.3f}s"
    )
    for profile in ("core", "challenge"):
        print(
            f"  {profile}: "
            f"{result.required_hits[profile]}/{result.required_total[profile]} richiesti · "
            f"{result.forbidden_hits[profile]} vietati"
        )
    for detail in result.details:
        print(f"    - {detail}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "models",
        nargs="*",
        default=["it_core_news_sm", "it_core_news_lg"],
    )
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()

    results = [evaluate(model, max(1, args.repeat)) for model in args.models]
    for result in results:
        print_result(result)

    by_name = {result.model: result for result in results}
    small = by_name.get("it_core_news_sm")
    large = by_name.get("it_core_news_lg")
    if small and large:
        core_is_not_worse = (
            small.required_hits["core"] >= large.required_hits["core"]
            and small.forbidden_hits["core"] <= large.forbidden_hits["core"]
        )
        core_is_complete = (
            small.required_hits["core"] == small.required_total["core"]
            and small.forbidden_hits["core"] == 0
        )
        if not (core_is_not_worse and core_is_complete):
            print("\nESITO: il modello small non soddisfa la soglia per la build standard.")
            return 1
        print(
            "\nESITO: il modello small eguaglia il large sui casi core. "
            "Le differenze challenge restano informative e non bloccanti."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
