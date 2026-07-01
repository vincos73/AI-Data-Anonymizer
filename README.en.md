# OMISSIS

OMISSIS is a privacy-first tool for anonymizing Italian documents before sharing them with AI chatbots, cloud services, collaborators, or external systems.

The main product is the desktop app: install it, open a document, anonymize it locally on your computer. The software does not send files or text to external APIs.

The web app exists only as an advanced option for developers, local demos, or self-hosted deployments on infrastructure you control.

## What It Does

- Detects and anonymizes common Italian personal and business data.
- Works with pasted text and uploaded documents.
- Offers a standard mode and a maximum-protection mode.
- In standard mode, preserves initials for people, organizations, addresses, and territorial bodies.
- In standard mode, does not anonymize dates.
- In maximum-protection mode, replaces detected personal data with full placeholders and also redacts common date formats.
- Keeps `.docx` formatting as much as possible while replacing sensitive text.
- Provides a desktop app, with a self-hosted web app for advanced use cases.

Detected data includes:

- email addresses
- PEC certified email addresses, separated from ordinary email when the domain or nearby context indicates PEC
- Italian phone numbers, including common formats with spaces, dots, dashes, or slashes
- IBANs, including spaced Italian IBANs
- codice fiscale
- partita IVA
- SDI, recipient, and office unique codes when explicit context is present
- Italian health card numbers when explicit context is present
- identity documents, passports, and driving licences when explicit context is present
- vehicle plates when explicit context is present
- protocol, case, file, or application numbers when explicit context is present
- Italian addresses with strong address signals
- people names only with strong context, including birth/residence and payment-recipient contexts
- company names with legal forms such as `S.r.l.`, `S.p.A.`, `S.n.c.`, `S.a.s.`, cooperatives and similar
- territorial bodies such as `Provincia di Potenza`, `Comune di Roma`, `Regione Basilicata`
- common date formats in maximum-protection mode

## Why It Exists

Many people paste contracts, letters, reports, invoices, and case notes into AI tools. Those documents often contain personal data, company names, fiscal identifiers, addresses, emails, or phone numbers.

OMISSIS helps prepare a safer version of those documents before they leave your computer. In normal use, the recommended path is the desktop app.

It is not a legal compliance product and it does not guarantee perfect anonymization. Always review the output before sharing sensitive documents.

## Supported Formats

| Format | Support |
| --- | --- |
| `.txt`, `.md`, `.csv` | Reads and saves anonymized text files |
| `.docx` | Reads and saves anonymized Word documents, preserving formatting where possible |
| `.pdf` | Extracts selectable text for analysis and saves a rasterized redacted PDF; the visual layout is preserved, but final text is not selectable. Scanned or image-only PDFs must be converted with OCR first. |
| `.doc` | Supported on macOS only; converted to `.docx` before anonymization |

On Windows, convert legacy `.doc` files to `.docx` before using the desktop app.

## Privacy Model

The desktop app processes documents locally. It does not send text or files to external APIs.

The web app is not required for normal desktop use. If you run it locally on `127.0.0.1`, it stays on your computer as a browser interface. If you publish it on a server, text submitted to the web app is sent to that server. For sensitive documents, run it only on infrastructure you control and use HTTPS.

The app rejects scanned or image-only PDFs when no selectable text can be extracted, so users do not mistake an unread PDF for a safely anonymized one. Redacted PDFs are rebuilt as page images with permanent blackouts: this avoids leaving original text under visual overlays, but the final PDF text is not copyable or searchable.

For `.docx` files, the app anonymizes visible document text and also sanitizes common hidden Office content such as metadata, comments, text boxes, footnotes, endnotes, and selected revision text.

## Desktop App

Download a release artifact from the repository Releases page when available.

Typical workflow:

1. Open the app.
2. Load a supported document, drag it into the window, or paste text.
3. Analyze the content.
4. Anonymize it.
5. Review the final report with the selected mode, detected data count, and safety warnings.
6. Save the anonymized result.

The desktop app defaults to maximum-protection mode, which is the recommended choice before sharing content with ChatGPT or other AI tools.

### macOS

The macOS build creates:

- `OMISSIS.app`
- `OMISSIS.dmg`

Unsigned builds may be blocked by Gatekeeper. If macOS warns that the developer is unidentified, right-click the app and choose **Open**.

### Windows

The Windows build creates:

- `OMISSIS.exe`
- `OMISSIS-Windows.zip`

The Windows desktop app supports `.txt`, `.md`, `.csv`, `.docx`, and `.pdf`.

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

The web app also defaults to **maximum protection** and shows a short final checklist before sharing.

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

Build Windows package from PowerShell:

```powershell
.\scripts\build_windows_app.ps1
```

The GitHub Actions workflow `build-windows` can also create the Windows zip manually or attach it to a release when a tag such as `v0.3.0` is published.

## Tests

```bash
pip install -e ".[desktop,web]"
python -m unittest discover -s tests -v
```

The test suite covers Italian false positives, person and organization recognition, territorial bodies, PEC addresses, protocol/case numbers, structured identifiers, standard and maximum-protection anonymization, document anonymization, `.docx` structure and formatting preservation, hidden `.docx` metadata/content sanitization, unreadable/scanned PDF rejection, and rasterized PDF redaction without extractable original text.

## Project Status

This is an early open-source release. The engine is rule-based and intentionally conservative. Contributions are welcome, especially for:

- reducing Italian false positives;
- improving document formatting preservation;
- adding carefully tested recognizers;
- improving packaging and release automation.

## License

MIT License. See [LICENSE](LICENSE).
