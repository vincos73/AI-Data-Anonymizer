# Repository Guidelines

## Project Structure & Module Organization

OMISSIS is a Python desktop and self-hosted web app for local anonymization of Italian documents.

- `src/privacy_guardian/`: application code.
  - `app.py`: PySide6 desktop UI.
  - `web_app.py`: FastAPI local/self-hosted web UI.
  - `italian_privacy_engine.py`, `privacy_engine.py`, `ner_recognizer.py`: detection/anonymization logic.
  - `document_service.py`: TXT/DOCX/PDF loading, OCR, and export.
  - `activity_log.py`, `reversible.py`: local audit log and reversible maps.
  - `assets/`, `web_static/`: bundled logos and web assets.
- `tests/`: unit and integration tests.
- `scripts/`: local build helpers for macOS, Windows, icons, and DMG layout.
- `assets/`: generated app icons.
- `documenti_di_prova/`: synthetic Italian test documents.

Do not commit `dist/`, `build/`, `.venv/`, caches, or local-only design/source folders unless explicitly requested.

## Build, Test, and Development Commands

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[desktop,web]"
python -m unittest discover -s tests -v
```

Run the desktop app:

```bash
ai-data-anonymizer
```

Run the local web app:

```bash
ai-data-anonymizer-web
```

Build packages:

```bash
./scripts/build_macos_app.sh
./scripts/build_windows_app.ps1
```

macOS notarization is enabled only when the Apple Developer secrets documented in `README.md` are configured.

## Coding Style & Naming Conventions

Use Python 3.10+ with 4-space indentation, type hints, dataclasses for structured values, and small focused functions. Prefer explicit names such as `ReversibleMapEntry` or `anonymize_loaded_document`. Keep UI text in Italian for user-facing desktop/web flows. Avoid broad refactors when fixing targeted recognizer or document-export behavior.

## Testing Guidelines

Tests use `unittest` in `tests/test_italian_privacy_engine.py`. Add regression tests for every recognizer, document format, OCR branch, reversible-map behavior, or security-sensitive change. Use synthetic data only. For document tests, verify both output text and absence of original sensitive values.

## Commit & Pull Request Guidelines

Recent commits use short imperative Italian messages, for example `Correggi export PDF e testo modificato` or `Aggiungi notarizzazione macOS`. Keep commits focused and include docs/tests when behavior changes. Pull requests should describe the user impact, list validation commands, mention packaging/release effects, and include screenshots for UI changes.

## Security & Privacy Notes

The app must remain local-first: do not add external API calls, telemetry, analytics, or cloud OCR for document content. Activity logs must store metadata only. Reversible maps contain original values and must remain encrypted and user-controlled.
