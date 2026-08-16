# Superlight Invoice

A deliberately small, self-contained tool for invoices, payments and receipts
without the accounting software. Select a company, issue an invoice, then
record one or more payments against it as receipts. Everything runs as one
local Python process — Node.js is only needed to rebuild the interface.

The project is open source under the GNU Affero General Public License v3.0
only (`AGPL-3.0-only`). It is designed for local use and does not include
authentication or hosted multi-user access controls.

## Business flow

```text
Company
  └─ Clients
      └─ Invoice
          └─ one or more Receipts (each records a payment)
```

- No login is required. Choose a company when the interface opens and use
  **Switch company** in the header to move to another ledger.
- Clients, documents, numbering, settings and PDFs are isolated by company.
- Add a company from the company chooser with its legal name and optional
  business name; complete its tax, address and bank details under Settings.

- An invoice is issued to a client and carries lines, GST and a due date. A
  GST-registered issuer can mark each line as taxable or GST-free, including
  invoices that contain both.
- A receipt records money actually received against that invoice. Several
  receipts can apply to one invoice, so part payments are supported.
- The invoice status follows the money automatically: `issued` →
  `partially paid` → `paid`. A receipt can never take more than the
  outstanding balance.
- An invoice can be edited only while it has no receipts. Once money is
  recorded against it, void the receipts first.
- Voiding an invoice voids its receipts with it. Voiding a receipt reopens the
  invoice balance. Both require an operator and a reason, and both are
  reversible via Restore.
- Every issued PDF is stored as an immutable snapshot. Later changes to
  Settings or to a client record never rewrite a document already sent.

## Layout

```text
backend/    FastAPI + SQLAlchemy + a single SQLite database
frontend/   React source, only needed when rebuilding the interface
backend/app/static/   the compiled interface shipped with the backend
install.*   one-time Python environment setup
start.*     the local launcher
build.*     developer-only interface rebuild
_datadir.*  the shared DATA_DIR resolver every script uses
```

## Run on Windows

```powershell
.\install.ps1
.\start.ps1
```

## Windows desktop app

The desktop edition opens the same interface in a native WebView2 window and
keeps the FastAPI server private to that application session. Install and run
the development version with the `.cmd` launchers (these also work when local
PowerShell script execution is disabled):

```bat
install-desktop.cmd
run-desktop.cmd
```

To create a distributable, self-contained application folder:

```bat
build-desktop.cmd
```

End users should download `SuperlightInvoice-<version>-Setup.exe` from the
project website or GitHub Releases. It installs for the current Windows user,
does not require administrator access, adds a Start menu shortcut and includes
an uninstaller. The target PC does not need Python or Node.js, but it does need
the Microsoft WebView2 Runtime (included in current Windows 11 installations
and most supported Windows 10 systems).

The developer build produces `dist\SuperlightInvoice\SuperlightInvoice.exe`. Keep
the whole `SuperlightInvoice` folder together; the executable cannot run without
its adjacent `_internal` directory. To turn that folder into the single-file
installer after installing Inno Setup 6:

```powershell
.\scripts\build-windows-installer.ps1 -Version 2.1.0
```

GitHub's release workflow builds both the recommended Setup EXE and a portable
ZIP, then publishes their SHA-256 checksums and artifact attestations.

The desktop app asks for a data folder before opening the main window. The
dialog shows the folder used on the previous launch and opens the native folder
picker at that location. Changing folders opens a different database; it does
not move the contents of the previous folder. Cancel exits without opening any
database.

An installed/frozen desktop build suggests `%LOCALAPPDATA%\InvoiceReceipts`
by default. `DATA_DIR` still supplies the initial choice when explicitly set.
The confirmed folder is remembered in
`%LOCALAPPDATA%\InvoiceReceipts\desktop-preferences.json`. This internal folder
name intentionally remains unchanged after the Superlight Invoice rename, so
upgrades keep the last selected data folder without a migration step.

## Run on Linux/macOS

```bash
./install.sh
./start.sh
```

Open <http://127.0.0.1:8790>. Fill in Settings first: the legal name, ABN and
bank details are printed on every document; the business name is optional. A
GST-registered business needs a valid ABN before anything can be issued.

## Where the data lives

All data — the SQLite database and every stored PDF — sits in one directory.
The browser/server scripts resolve it as follows:

```text
an existing DATA_DIR environment variable  >  a DATA_DIR line in .env  >  ./.data
```

The desktop launcher confirms its directory interactively on every launch. Its
initial suggestion is resolved from `DATA_DIR`, then the last confirmed desktop
folder, then `.env`, then the platform default.

Copy `.env.example` to `.env` and set `DATA_DIR` to keep data outside the
project (on another drive, or in a folder that is already backed up). Because
`_datadir.ps1` / `_datadir.sh` is the single source of that rule, a future
script cannot silently target a different folder from the launcher.

To back up, stop the app and copy the whole data directory. It contains one
`invoices.db` file with every company's records and stored PDFs inside it.

## Rebuilding the interface

Only needed when changing files under `frontend/`:

```powershell
.\build.ps1
```

Output goes to `backend/app/static` and must travel with the project.

## Verify

```powershell
cd backend
.venv\Scripts\python.exe -m pip install pytest httpx pypdf
.venv\Scripts\python.exe -m pytest -q
```

## Deployment boundary

Unauthenticated company selection, bound to `127.0.0.1`. Company separation is
for organising one local operator's records, not an access-control boundary.
Do not expose port 8790 to a LAN, a reverse proxy or the internet. The app
rejects requests whose `Host` header is not loopback, but that is a safety net,
not a substitute for keeping it local.

## Product boundary

Superlight Invoice intentionally sits between Word/Excel templates and a full
accounting system. It manages company and client details, invoices, GST,
payments, receipts, immutable PDFs and their audit trail. It does not provide a
general ledger, bank feeds, reconciliation, payroll, inventory, BAS lodgement
or financial statements. See [`docs/PRODUCT_SCOPE.md`](docs/PRODUCT_SCOPE.md)
for the maintained scope and roadmap rules.

## Privacy and responsibility

- The selected data directory can contain company details, client information,
  invoices, receipts and stored PDFs. Never commit or attach that directory to
  a bug report.
- Back up the complete data directory before upgrading or changing storage
  locations.
- This software is provided without warranty and is not tax, accounting or
  legal advice. Users remain responsible for checking that generated documents
  satisfy the rules that apply to them.
- Security issues should be reported privately using the process in
  `SECURITY.md`, without including real customer data.

## Contributing

Contributions are welcome. Read `CONTRIBUTING.md` before opening a pull request.
The supported deployment boundary is local-only unless a proposal explicitly
adds authentication, authorization and a reviewed network threat model.

## License

Copyright © 2026 Superlight Invoice contributors.

This project is licensed under `AGPL-3.0-only`. See `LICENSE` for the complete
terms and `THIRD_PARTY_NOTICES.md` for bundled dependency and font notices.
