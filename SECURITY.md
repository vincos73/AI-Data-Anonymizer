# Security and privacy

AI Data Anonymizer is designed to run locally or on infrastructure controlled by the user.

The app does not call external AI, OCR, analytics, or document-processing APIs. Desktop processing stays on the local machine. The self-hosted web app processes text on the server where it is deployed.

## Anonymization expectations

AI Data Anonymizer is a risk-reduction tool, not a legal guarantee of anonymous data.

- Standard mode preserves initials for selected entities and keeps dates visible.
- Maximum-protection mode replaces detected entities with full placeholders and also redacts common date formats.
- Users should always review anonymized output before sharing it with chatbots, cloud tools, collaborators, or external systems.
- Scanned or image-only PDFs are rejected when no selectable text can be extracted. Run OCR first, then anonymize the OCR-enabled PDF.
- `.docx` files are sanitized for visible text and common hidden Office content such as metadata, comments, text boxes, footnotes, endnotes, and selected revision text.

## Public hosted services

If you expose the web app publicly, uploaded or pasted content reaches your server. That may create legal, security, and operational responsibilities. For sensitive documents, prefer local desktop usage or self-hosting inside a trusted environment.

Minimum recommendations for a hosted deployment:

- use HTTPS;
- require authentication for non-demo deployments;
- disable request body logging in reverse proxies and app servers;
- do not add analytics, session replay, or third-party scripts to pages that process documents;
- set strict upload limits;
- process documents in memory where possible;
- delete temporary files immediately if you add any file-upload endpoint;
- publish clear privacy terms for users.

## Reporting issues

Open a GitHub issue for non-sensitive bugs. For security-sensitive reports, use a private disclosure channel configured in the repository before sharing examples containing real personal data.
