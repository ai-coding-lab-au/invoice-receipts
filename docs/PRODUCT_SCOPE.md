# Superlight Invoice product scope

## Product promise

Superlight Invoice is the shortest reliable path from work completed to an
invoice, then from payment received to a receipt. It is local-first, requires
no account, supports several companies in one data file, and keeps issued PDFs
as immutable records.

The public positioning is:

> Invoices, payments and receipts — without the accounting software.

## Core scope

- Multiple companies and clients without login or cloud setup.
- Australian Invoice and Tax Invoice documents with ABN details.
- Taxable and GST-free treatment on each invoice line.
- Zero-value invoices, part payments and multiple receipts per invoice.
- Formal receipt PDFs linked back to the source invoice.
- Void and restore actions with an audit trail.
- Immutable PDF snapshots and document search.
- Explicit data-folder selection, backup and restore guidance.
- A one-click Windows installer and a portable build.

## Explicitly out of scope

- General ledger, chart of accounts and journal entries.
- Accounts payable and expense management.
- Bank feeds and bank reconciliation.
- Payroll and superannuation.
- Inventory and purchasing.
- BAS preparation or lodgement.
- Profit-and-loss, balance-sheet or other financial statements.
- Hosted multi-user accounts, permissions or collaboration.
- Embedded payment processing.

These are product boundaries, not a backlog. A proposed feature that requires
one of them should normally integrate with or export to an accounting product
instead of recreating that product inside Superlight Invoice.

## Roadmap filter

A feature belongs in the core only when it materially improves at least one of
these workflows without turning the app into an accounting package:

1. Create and send a correct invoice.
2. Record payment and issue a correct receipt.
3. Correct, void, find, export or back up those records safely.

Credit notes/refunds, CSV export and in-app backup/restore are the next
high-priority gaps. Email delivery, Peppol eInvoicing and optional cloud backup
can follow as isolated integrations after the local workflow is complete.

## Compliance posture

The software makes GST treatment explicit and preserves issued documents, but
it is not tax or accounting advice. Users remain responsible for classifying
their supplies and checking that each document satisfies the rules that apply
to the transaction.
