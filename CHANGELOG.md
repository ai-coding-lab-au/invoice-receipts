# Changelog

All notable changes to this project will be documented in this file. The format
is based on Keep a Changelog and the project uses Semantic Versioning.

## [Unreleased]

### Added

- Open-source repository governance, security and release documentation.
- Automated backend, frontend and Windows release workflows.

### Changed

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
