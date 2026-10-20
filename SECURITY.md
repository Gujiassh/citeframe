# Security

## Sensitive reports

Do not post secrets, private files, user data, or exploit details in public issues. Ask a maintainer for a private reporting channel using a minimal public message without vulnerability details.

Private reports should include affected version, deployment assumptions, impact, and a synthetic reproduction. Revoke/rotate exposed credentials promptly; deleting a public message does not make them safe.

## Deployment precautions

- Replace development passwords, internal tokens, and signing placeholders.
- Keep environment files/provider keys out of version control and logs.
- Persist/restrict the model encryption key and back it up separately.
- Expose only configured Web/Caddy; keep API, database, storage, and metrics private.
- Use TLS for public/model endpoints; review private-origin allowances.
- Treat documents/model output as untrusted and verify source evidence.
- Back up database/storage together and test empty-target recovery.

See [deployment](docs/deployment/README.md), [model controls](docs/guides/model-configuration.md), and [authorization](docs/architecture/workspace-access.md). Preview and available tests do not establish security coverage for every deployment.
