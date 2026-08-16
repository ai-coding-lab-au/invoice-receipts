# Changelog

All notable changes to this project will be documented in this file. The format
is based on Keep a Changelog and the project uses Semantic Versioning.

## [Unreleased]

## [2.0.0] - 2026-08-16

### Added

- Open-source repository governance, security and release documentation.
- Automated backend, frontend and Windows release workflows.
- Per-line taxable or GST-free treatment, including mixed invoices and clear
  line classification on Tax Invoice PDFs.
- Multiple locally selected company ledgers without login.
- Interactive data-directory selection for the desktop application.
- Company-scoped clients, document numbering, invoices, receipts and settings.
- Immutable PDF snapshots and document audit history.
- Windows desktop packaging with an embedded local server and WebView2 window.

### Changed

- Product branding is now Superlight Invoice. The internal desktop preference
  folder remains `InvoiceReceipts` so upgrades keep the last selected data
  folder without migration.
- Updated the bundled React Router dependency to a patched release.
- Zero-value invoices are permitted.
- Invoice operator is optional while receipt and audit-sensitive actions retain
  their operator requirement.
- Invoice editing validation now provides persistent, visible feedback.
