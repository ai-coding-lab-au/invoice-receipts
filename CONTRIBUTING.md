# Contributing to Invoice & Receipts

Thank you for helping improve Invoice & Receipts. The project is a local-first
desktop and loopback web application. Changes should preserve that deployment
boundary unless a proposal also introduces authentication, authorization and a
reviewed network threat model.

## Before you start

- Search existing issues before opening a new one.
- Use fictional companies, clients, ABNs and documents in tests, screenshots and
  issue reports.
- Never attach `.env`, `invoices.db`, PDFs, logs or a real data directory.
- Discuss large schema, workflow or licensing changes in an issue first.

## Development setup

Python 3.11 or later and a current Node.js LTS release are required.

On Windows:

```powershell
.\install-desktop.cmd
cd frontend
npm ci
npm run build
cd ..\backend
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q --basetemp ..\.pytest-tmp-local
```

On Linux or macOS, use `./install.sh` and the equivalent `.venv/bin/python`
commands.

## Pull requests

1. Keep a change focused and explain the user-visible outcome.
2. Add or update tests for behavior changes.
3. Run the backend test suite and frontend production build.
4. Update `CHANGELOG.md` when behavior, storage or compatibility changes.
5. Do not commit generated databases, logs, build directories or release ZIPs.

The project uses the Developer Certificate of Origin 1.1. Sign off every commit
to certify that you have the right to submit it under the project license:

```bash
git commit -s -m "Describe the change"
```

## Coding expectations

- Prefer explicit validation and visible error messages over silent fallback.
- Preserve company scoping for every query and mutation.
- Treat issued PDFs and audit history as immutable business records.
- Keep the server bound to loopback and retain host-header protections.
- Avoid migrations that discard or rewrite user data without a tested recovery
  path.

## License

By contributing, you agree that your contribution is licensed under
`AGPL-3.0-only`, the license stated by this repository.
