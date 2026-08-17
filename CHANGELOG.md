# Changelog

All notable changes to this project will be documented in this file. The format
is based on Keep a Changelog and the project uses Semantic Versioning.

## [Unreleased]

### Added

- Native macOS development support with a Cocoa data-folder picker, branded
  app bundle, local launcher/build scripts and unsigned Apple Silicon and Intel
  CI artifacts.

## [2.2.1] - 2026-08-17

### Fixed

- The branded application icon is now applied consistently to the native
  Windows window, taskbar identity and installed shortcuts.
- Download PDF now opens the native Windows Save As dialog in the desktop app.
- The New client action in the invoice editor is now easier to identify.

## [2.2.0] - 2026-08-17

### Added

- Clients can be created from the invoice editor and selected immediately
  without losing the invoice draft.
- A dedicated Superlight Invoice icon is embedded in the Windows application
  and installer.

### Changed

- Replaced the real-world ABN used in form placeholders with the fictional
  format example `12 345 678 901`.
- Nested invoice and client dialogs now keep keyboard focus in the active
  dialog and cannot be dismissed while a client is being saved.

## [2.1.0] - 2026-08-16

### Added

- Open-source repository governance, security and release documentation.
- Automated backend, frontend and Windows release workflows.
- Per-line taxable or GST-free treatment, including mixed invoices and clear
  line classification on Tax Invoice PDFs.

### Changed

- Product branding is now Superlight Invoice. The internal desktop preference
  folder remains `InvoiceReceipts` so upgrades keep the last selected data
  folder without migration.
- Updated the bundled React Router dependency to a patched release.
- Zero-value invoices are permitted.
- Invoice operator is optional while receipt and audit-sensitive actions retain
  their operator requirement.
- Invoice editing validation now provides persistent, visible feedback.

## [2.0.0] - 2026-08-16

### Added

- Multiple locally selected company ledgers without login.
- Interactive data-directory selection for the desktop application.
- Company-scoped clients, document numbering, invoices, receipts and settings.
- Immutable PDF snapshots and document audit history.
- Windows desktop packaging with an embedded local server and WebView2 window.
