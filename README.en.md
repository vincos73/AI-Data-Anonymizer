# OMISSIS

OMISSIS is a privacy-first tool for anonymizing Italian documents before sharing them with AI chatbots, cloud services, collaborators, or external systems.

The main product is the desktop app: install it, open a document, anonymize it locally on your computer. The software does not send files or text to external APIs.

The web app exists only as an advanced option for developers, local demos, or self-hosted deployments on infrastructure you control.

Current source version: **v0.6.14**. Published builds may temporarily have an earlier version; use the repository [Releases page](https://github.com/vincos73/AI-Data-Anonymizer/releases/latest) and check the version shown in the app.

## What It Does

- Detects and anonymizes common Italian personal and business data.
- Works with pasted text and uploaded documents.
- Offers a standard mode and a maximum-protection mode.
- Offers a reversible mode with numbered placeholders and a locally encrypted map in the desktop app.
- In standard mode, preserves initials while keeping territorial and academic institution roles readable for contextual understanding.
- In standard mode, does not anonymize dates.
- In maximum-protection mode, replaces detected personal data with full placeholders and also redacts common date formats.
- Keeps `.docx` formatting as much as possible while replacing sensitive text.
- Can convert PDF extraction into normalized text for stronger recognition and LLM-oriented `.txt` output.
- Uses a guided five-step workflow with one primary action at a time, from loading through final use.
- Shows a structured final safety report with protected-data counts, categories, mode, format, save state, and review warnings.
- Provides a desktop app, with a self-hosted web app for advanced use cases.

Detected data includes:

- email addresses
- PEC certified email addresses, separated from ordinary email when the domain or nearby context indicates PEC
- Italian phone numbers, including common formats with spaces, dots, dashes, or slashes, plus international numbers with a `+` prefix
- Italian and international IBANs, validated by checksum and per-country length, including spaced formats
- codice fiscale
- partita IVA
- SDI, recipient, and office unique codes when explicit context is present
- Italian health card numbers when explicit context is present
- identity documents, passports, and driving licences when explicit context is present
- vehicle plates when explicit context is present
- protocol, case, file, or application numbers when explicit context is present
- cadastral references such as sheet, parcel, map, subaltern, section, and cadastral category
- Italian addresses with strong address signals, including lowercase ones when a house number is present
- explicitly labelled Italian postal codes, and postal codes followed by a city
- Italian regions, provinces, and municipalities using the bundled ISTAT list updated on 21 February 2026, with contextual safeguards for ambiguous names
- people names with strong context, including birth/residence and payment-recipient contexts; desktop builds include the fully local `it_core_news_sm` spaCy model to catch additional people and locations without context, including foreign locations
- company names with legal forms such as `S.r.l.`, `S.p.A.`, `S.n.c.`, `S.a.s.`, cooperatives and similar
- territorial bodies such as `Provincia di Potenza`, `Comune di Roma`, `Regione Basilicata`
- common date formats in maximum-protection and reversible modes

## Why It Exists

Many people paste contracts, letters, reports, invoices, and case notes into AI tools. Those documents often contain personal data, company names, fiscal identifiers, addresses, emails, or phone numbers.

OMISSIS helps prepare a safer version of those documents before they leave your computer. In normal use, the recommended path is the desktop app.

It is not a legal compliance product and it does not guarantee perfect anonymization. Always review the output before sharing sensitive documents.

## Supported Formats

| Format | Support |
| --- | --- |
| `.txt`, `.md`, `.csv` | Reads and saves anonymized text files |
| `.docx` | Reads and saves anonymized Word documents, preserving formatting where possible |
| `.pdf` | Extracts text for analysis and saves a rasterized redacted PDF; mixed text/image pages can use local Tesseract OCR when available. |
| `.doc` | Supported on macOS only; converted to `.docx` before anonymization |

On Windows, convert legacy `.doc` files to `.docx` before using the desktop app.

## Privacy Model

The desktop app processes documents locally. It does not send text or files to external APIs.

See the Italian [security and privacy page](SICUREZZA.md) for the full operational model.

The desktop app keeps a local activity log available from **Strumenti > Registro attività**. It stores metadata only: timestamp, operation, mode, category counts, file extension, file size, and SHA-256 hashes when files are available. It does not store original text, anonymized text, detected values, previews, or full file paths. The same dialog can disable logging, set its retention limit, or clear it.

The reversible mode creates a password-encrypted local `.omissis-map` file. It contains the sensitive correspondence between numbered placeholders and original values, so it should be kept private and never uploaded to external AI or cloud services. Results, maps, and local settings use atomic replacement; sensitive local files are owner-only on supported systems.

The web app is not required for normal desktop use. If you run it locally on `127.0.0.1`, it stays on your computer as a browser interface. If you publish it on a server, text submitted to the web app is sent to that server. For sensitive documents, run it only on infrastructure you control and use HTTPS.

Scanned or image-only PDFs require OCR. OMISSIS can use **local Tesseract OCR** when it is installed on the computer; it does not call external OCR services. If Tesseract is unavailable or does not find reliable text, the app rejects the PDF so users do not mistake an unread file for a safely anonymized one. Redacted PDFs are rebuilt as page images with permanent blackouts: this avoids leaving original text under visual overlays, but the final PDF text is not copyable or searchable.

For `.docx` files, the app anonymizes visible document text and also sanitizes common hidden Office content such as metadata, comments, text boxes, footnotes, endnotes, and selected revision text.

## Desktop App

Download a release artifact from the repository Releases page when available.

Published desktop builds include the lightweight Italian spaCy model `it_core_news_sm`, so local NER works without an additional installation. Source installations can add it with:

```bash
pip install "ai-data-anonymizer[ner]"
python -m spacy download it_core_news_sm
```

Manually installed `it_core_news_md` and `it_core_news_lg` models are supported too. Run `python scripts/benchmark_ner_models.py` to compare the small and large models on OMISSIS's synthetic regression cases.

In the v0.6.3 synthetic benchmark, both the small and large models detect all 25 expected entities in the core Italian and administrative cases, without the checked false positives. The large model remains better on some international names with diacritics or multiple components and can be installed manually when those documents are prevalent. This benchmark lowers regression risk but does not replace human review before sharing a document.

Typical workflow:

1. Open the app.
2. Load a supported document, drag it into the window, or paste text.
3. Choose the protection mode and analyze the content.
4. Review every detected value. Checked means “will be anonymized”; unchecked means “will remain visible”. Search, filter, or add a missing selection manually.
5. Click **Ho controllato, continua**, then **Crea copia protetta**. The side workflow always shows the current step.
6. Review the structured final report with protected categories, mode, format, save state, and safety warnings. The detections list closes to focus on the original/protected comparison and can be reopened with **Modifica selezioni**.
7. Read the result before sharing it, then use **Copia per ChatGPT** for text or **Salva copia protetta** for a document. The original text or file is not modified.
8. If you need an audit trail, open **Strumenti > Registro attività**.
9. If you use reversible mode, save the local encrypted map from **Strumenti > Salva mappa reversibile**.

The desktop and web apps default to Standard mode to preserve more of the document structure, roles, and context. Choose maximum protection for high-risk documents or when redacting as many identifying details as possible matters more than readability.

Document loading, OCR, analysis, and anonymization show progress and can be cancelled. A cancelled or failed operation preserves the previous result. Converting a PDF to normalized text automatically starts a fresh analysis.

For PDFs, users can preserve the original format as a rasterized PDF with permanent redactions or convert it to normalized text. Text conversion drops the original layout but makes the result easier to review, copy, and use with ChatGPT or another AI tool.

Main shortcuts: `Cmd/Ctrl+O` loads a document, `Cmd/Ctrl+Enter` runs the current step, `Cmd/Ctrl+F` searches detected data, `Space` includes or excludes the selected row, and `Cmd/Ctrl+S` saves the result. The full review guide is available from the Help menu.

Reversible mode is available for pasted text, `.txt`, and `.docx` in the desktop app. Use maximum protection for `.md`, `.csv`, and PDF files because those outputs are not reversible.

### macOS

The macOS build creates:

- `OMISSIS.app`
- `OMISSIS.dmg`

Unsigned or non-notarized builds may be blocked by Gatekeeper. The GitHub release workflow can sign and notarize the macOS DMG when Apple Developer secrets are configured.

### Windows

The Windows build creates:

- `OMISSIS.exe`
- `OMISSIS-Setup.exe`
- `OMISSIS-Windows.zip`

The Windows desktop app supports `.txt`, `.md`, `.csv`, `.docx`, and `.pdf`.

For the simplest installation, download `OMISSIS-Setup.exe`, complete the guided setup, and start OMISSIS from the Start menu. The installer works per user without administrator privileges. `OMISSIS-Windows.zip` remains available as a portable alternative. An unsigned installer can still trigger a Microsoft Defender SmartScreen warning; Authenticode signing is a separate distribution step.

## Run From Source

Requirements:

- Python 3.10, 3.11, 3.12, or 3.13
- Git

```bash
git clone https://github.com/vincos73/AI-Data-Anonymizer.git
cd AI-Data-Anonymizer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[desktop]"
ai-data-anonymizer
```

On Windows PowerShell:

```powershell
git clone https://github.com/vincos73/AI-Data-Anonymizer.git
cd AI-Data-Anonymizer
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[desktop]"
ai-data-anonymizer
```

To develop the web app and API too:

```bash
pip install -e ".[desktop,web]"
```

## Advanced Option: Self-Hosted Web App

Most users should use the desktop app. The web app is useful when you want a browser interface on your own machine, an internal network deployment, or a Docker-based setup.

Run locally:

```bash
pip install -e ".[web]"
ai-data-anonymizer-web
```

Then open:

```text
http://127.0.0.1:8080
```

The web app supports pasted text and supported document uploads, then downloads the anonymized file. By default it accepts up to **100,000 characters** of extracted text and **10 MB** per file.

The web app also defaults to **Standard** and shows a short final checklist before sharing. Choose maximum protection when minimizing identifying details matters more than readability.

Reversible mode and encrypted-map restoration are available only in the desktop app. The web app exposes Standard and Maximum protection only, avoiding the transmission of passphrases and maps to a server. A future version may add encryption fully in the browser.

Run with Docker:

```bash
docker build -t ai-data-anonymizer .
docker run --rm -p 8080:8080 ai-data-anonymizer
```

Recommended production setup:

- serve behind HTTPS;
- require authentication for non-demo deployments;
- disable request body logging in reverse proxies;
- avoid analytics, session replay, or third-party scripts;
- use conservative upload limits;
- publish clear privacy terms for users.

## Build Desktop Packages

Build macOS package:

```bash
./scripts/build_macos_app.sh
```

The build creates a DMG when macOS allows volume creation. In isolated environments where `hdiutil` cannot mount it, the script preserves the signed `.app` and automatically creates a versioned installable ZIP.

### macOS Signing and Notarization

To distribute OMISSIS without Gatekeeper warnings, an Apple Developer Program account and a **Developer ID Application** certificate are required.

The GitHub workflow supports these secrets:

- `APPLE_DEVELOPER_ID_CERTIFICATE_BASE64`: base64-encoded Developer ID Application `.p12` certificate;
- `APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD`: `.p12` password;
- `APPLE_DEVELOPER_ID_APPLICATION`: codesign identity, for example `Developer ID Application: Name Surname (TEAMID)`;
- `APPLE_ID`: Apple Developer account email;
- `APPLE_TEAM_ID`: Apple Team ID;
- `APPLE_APP_SPECIFIC_PASSWORD`: app-specific password generated from the Apple account;
- `BUILD_KEYCHAIN_PASSWORD`: temporary build keychain password.

When these secrets are available, the macOS build signs the app, signs the DMG, submits it to Apple with `notarytool`, staples the notarization ticket, and uploads the notarized DMG to GitHub Releases.

Build Windows package from PowerShell:

```powershell
.\scripts\install_inno_setup.ps1
.\scripts\build_windows_app.ps1
```

The build creates `dist\OMISSIS-Setup.exe` and the portable `dist\OMISSIS-Windows.zip`. The Inno Setup bootstrap downloads the pinned official release and verifies its SHA-256 hash before running it.

The unified GitHub Actions release workflow checks version alignment, builds both macOS and Windows, and publishes the release only after both artifacts are available.

## Tests

```bash
pip install -e ".[desktop,web]"
python -m unittest discover -s tests -v
```

The test suite covers Italian false positives, person and organization recognition, territorial bodies, PEC addresses, protocol/case numbers, structured identifiers, standard, maximum-protection and desktop reversible anonymization, encrypted reversible maps, document anonymization, `.docx` structure and formatting preservation, hidden `.docx` metadata/content sanitization, optional local OCR for scanned and mixed PDF pages, unreadable PDF rejection, and rasterized PDF redaction without extractable original text.

## Project Status

OMISSIS is an evolving open-source project. The engine is rule-based and intentionally conservative. Contributions are welcome, especially for:

- reducing Italian false positives;
- improving document formatting preservation;
- improving local OCR for scanned PDFs and images;
- refining reversible mode and AI-response reconstruction;
- adding carefully tested recognizers;
- improving signing and notarization of published builds.

## License

MIT License. See [LICENSE](LICENSE).
