# Security and privacy

AI Data Anonymizer is designed to run locally or on infrastructure controlled by the user.

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
