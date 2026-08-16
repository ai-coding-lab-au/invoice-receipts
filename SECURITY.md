# Security policy

## Supported versions

Security fixes are made on the default branch and included in the next release.
Only the latest published release is supported.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability.

Use GitHub Private Vulnerability Reporting from the repository's **Security**
tab. Until the public repository exists, contact the repository owner privately
using the contact method on their GitHub profile.

Include:

- the affected version and operating system;
- a minimal reproduction using fictional data;
- the expected impact;
- any suggested mitigation.

Never send a real database, PDF, log, company identity or client information.
The maintainers will acknowledge the report, assess its severity and coordinate
a fix and disclosure where appropriate.

## Security boundary

Superlight Invoice is designed for one trusted local operator. It has no login
and its company selector is an organisational boundary, not an access-control
boundary. The backend must remain bound to `127.0.0.1`; exposing it to a LAN,
reverse proxy or the internet is unsupported.

The selected data directory contains sensitive business records. Users are
responsible for operating-system access controls, backups, device security and
secure disposal of exported data.
