# AI Data Anonymizer

AI Data Anonymizer is a privacy-first tool for anonymizing Italian documents before sharing them with AI chatbots, cloud services, collaborators, or external systems.

It runs locally on your computer, or on infrastructure you control. The project focuses on high-precision Italian anonymization rules: when a match is uncertain, the app prefers not to anonymize rather than risk changing harmless text.

## What It Does

- Detects and anonymizes common Italian personal and business data.
- Works with pasted text and uploaded documents.
- Offers a standard mode and a maximum-protection mode.
- In standard mode, preserves initials for people, organizations, addresses, and territorial bodies.
- In standard mode, does not anonymize dates.
- In maximum-protection mode, replaces detected personal data with full placeholders and also redacts common date formats.
- Keeps `.docx` formatting as much as possible while replacing sensitive text.
- Provides a desktop app and a self-hosted web app.

Detected data includes:

- email addresses
- Italian phone numbers, including common formats with spaces, dots, dashes, or slashes
- IBANs, including spaced Italian IBANs
- codice fiscale
- partita IVA
- Italian addresses with strong address signals
- people names only with strong context, including birth/residence and payment-recipient contexts
- company names with legal forms such as `S.r.l.`, `S.p.A.`, `S.n.c.`, `S.a.s.`, cooperatives and similar
- territorial bodies such as `Provincia di Potenza`, `Comune di Roma`, `Regione Basilicata`
- common date formats in maximum-protection mode

## Why It Exists

Many people paste contracts, letters, reports, invoices, and case notes into AI tools. Those documents often contain personal data, company names, fiscal identifiers, addresses, emails, or phone numbers.

AI Data Anonymizer helps prepare a safer version of those documents before they leave your computer or your controlled environment.

It is not a legal compliance product and it does not guarantee perfect anonymization. Always review the output before sharing sensitive documents.

## Supported Formats

| Format | Support |
| --- | --- |
| `.txt`, `.md`, `.csv` | Reads and saves anonymized text files |
| `.docx` | Reads and saves anonymized Word documents, preserving formatting where possible |
| `.pdf` | Extracts text and creates a new anonymized PDF; original PDF layout may not be preserved. Scanned or image-only PDFs must be converted with OCR first. |
| `.doc` | Supported on macOS only; converted to `.docx` before anonymization |

On Windows, convert legacy `.doc` files to `.docx` before using the desktop app.

## Privacy Model

The desktop app processes documents locally. It does not send text or files to external APIs.

The web app is designed for self-hosting. It disables access logs in the app, avoids analytics, and sends no content to third-party services. However, text submitted to the web app is still sent to the server that hosts it. For sensitive documents, run it only on infrastructure you control and use HTTPS.

The app rejects scanned or image-only PDFs when no selectable text can be extracted, so users do not mistake an unread PDF for a safely anonymized one. Run OCR first, then anonymize the OCR-enabled PDF.

For `.docx` files, the app anonymizes visible document text and also sanitizes common hidden Office content such as metadata, comments, text boxes, footnotes, endnotes, and selected revision text.

## Desktop App

Download a release artifact from the repository Releases page when available.

Typical workflow:

1. Open the app.
2. Load a supported document or paste text.
3. Analyze the content.
4. Anonymize it.
5. Review the final report with the selected mode, detected data count, and safety warnings.
6. Save the anonymized result.

### macOS

The macOS build creates:

- `AI Data Anonymizer.app`
- `AI Data Anonymizer.dmg`

Unsigned builds may be blocked by Gatekeeper. If macOS warns that the developer is unidentified, right-click the app and choose **Open**.

### Windows

The Windows build creates:

- `AI Data Anonymizer.exe`
- `AI-Data-Anonymizer-Windows.zip`

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
pip install -e ".[desktop,web]"
ai-data-anonymizer
```

On Windows PowerShell:

```powershell
git clone https://github.com/vincos73/AI-Data-Anonymizer.git
cd AI-Data-Anonymizer
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[desktop,web]"
ai-data-anonymizer
```

## Self-Hosted Web App

Run locally:

```bash
pip install -e ".[web]"
ai-data-anonymizer-web
```

Then open:

```text
http://127.0.0.1:8080
```

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

The GitHub Actions workflow `build-windows` can also create the Windows zip manually or attach it to a release when a tag such as `v0.2.0` is published.

## Tests

```bash
python -m unittest discover -s tests -v
```

The test suite covers Italian false positives, person and organization recognition, territorial bodies, structured identifiers, standard and maximum-protection anonymization, document anonymization, `.docx` formatting preservation, hidden `.docx` metadata/content sanitization, and unreadable/scanned PDF rejection.

## Project Status

This is an early open-source release. The engine is rule-based and intentionally conservative. Contributions are welcome, especially for:

- reducing Italian false positives;
- improving document formatting preservation;
- adding carefully tested recognizers;
- improving packaging and release automation.

## License

MIT License. See [LICENSE](LICENSE).
