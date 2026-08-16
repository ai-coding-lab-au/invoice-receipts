import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, getActiveCompanyId, limitedList } from "../lib/api";
import {
  formatDate,
  formatMoney,
  pluralise,
  statusBadgeClass,
  statusLabel,
} from "../lib/format";
import type { DocumentRecord } from "../types/api";
import DocumentPreviewDialog from "../components/DocumentPreviewDialog";
import InvoiceEditorDialog from "../components/InvoiceEditorDialog";

type Tab = "invoice" | "receipt";
const STATUSES = ["ALL", "issued", "partially_paid", "paid", "void"] as const;

export default function InvoicesPage() {
  const companyId = getActiveCompanyId();
  const [tab, setTab] = useState<Tab>("invoice");
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("ALL");
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<DocumentRecord | null>(null);
  const [selected, setSelected] = useState<DocumentRecord | null>(null);

  const query = useQuery({
    queryKey: ["documents", companyId, tab, status, q],
    queryFn: async () =>
      limitedList(
        await api.get<DocumentRecord[]>("/documents", {
          params: {
            doc_type: tab,
            status: status === "ALL" ? undefined : status,
            q: q.trim() || undefined,
          },
        }),
      ),
  });

  const filtered = q.trim() !== "" || status !== "ALL";

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Invoices &amp; receipts</h1>
          <p className="mt-1 text-xs text-slate-500">
            Issue an invoice, then record payments against it as receipts.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setCreating(true)}>
          + New invoice
        </button>
      </header>

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b p-4">
          <div className="inline-flex overflow-hidden rounded border border-slate-300 text-sm">
            {(["invoice", "receipt"] as Tab[]).map((item) => (
              <button
                key={item}
                className={`px-3 py-1 ${tab === item ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`}
                onClick={() => {
                  setTab(item);
                  setStatus("ALL");
                }}
              >
                {item === "invoice" ? "Invoices" : "Receipts"}
              </button>
            ))}
          </div>
          <div className="inline-flex overflow-hidden rounded border border-slate-300 text-sm">
            {STATUSES.filter(
              (item) => tab === "invoice" || !["partially_paid", "paid"].includes(item),
            ).map((item) => (
              <button
                key={item}
                className={`px-3 py-1 ${status === item ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`}
                onClick={() => setStatus(item)}
              >
                {item === "ALL" ? "Any status" : statusLabel(item)}
              </button>
            ))}
          </div>
          <input
            className="input w-56"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search number or client…"
          />
        </div>

        <div className="border-b bg-slate-50 px-4 py-2.5 text-sm">
          <strong>{query.data?.total ?? 0}</strong>{" "}
          {pluralise(query.data?.total ?? 0, tab === "invoice" ? "invoice" : "receipt").replace(
            /^\d+\s/,
            "",
          )}
          {query.data?.truncated && (
            <span className="ml-2 text-amber-800">
              (showing the first {query.data.items.length})
            </span>
          )}
        </div>

        {query.isLoading && <p className="px-4 py-10 text-sm text-slate-500">Loading…</p>}
        {query.isError && (
          <p className="px-4 py-10 text-sm text-rose-700">Unable to load documents.</p>
        )}
        {query.data?.items.length === 0 && (
          <p className="px-4 py-12 text-center text-sm text-slate-500">
            {filtered
              ? "No documents match the current search or filter."
              : tab === "invoice"
                ? "No invoices yet. Click + New invoice to issue the first one."
                : "No receipts yet. Open an invoice and record a payment."}
          </p>
        )}

        {!!query.data?.items.length && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-600">
                <tr>
                  <th className="px-4 py-2">Date</th>
                  <th className="px-4 py-2">Number</th>
                  <th className="px-4 py-2">Client</th>
                  <th className="px-4 py-2">{tab === "invoice" ? "Due" : "Method"}</th>
                  <th className="px-4 py-2 text-right">
                    {tab === "invoice" ? "Outstanding" : "Amount"}
                  </th>
                  <th className="px-4 py-2 text-right">Total</th>
                  <th className="px-4 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((document) => (
                  <tr
                    key={document.id}
                    className="cursor-pointer border-t hover:bg-slate-50"
                    onClick={() => setSelected(document)}
                  >
                    <td className="px-4 py-2">{formatDate(document.issue_date)}</td>
                    <td className="px-4 py-2 font-mono font-medium text-emerald-800">
                      {document.doc_number}
                    </td>
                    <td className="px-4 py-2">{document.customer_name}</td>
                    <td className="px-4 py-2">
                      {tab === "invoice"
                        ? formatDate(document.due_date)
                        : document.payment_method ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {tab === "invoice" ? formatMoney(document.amount_outstanding) : "—"}
                    </td>
                    <td className="px-4 py-2 text-right font-medium tabular-nums">
                      {formatMoney(document.total)}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`rounded px-2 py-0.5 text-xs ${statusBadgeClass(document.status)}`}
                      >
                        {statusLabel(document.status)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {creating && (
        <InvoiceEditorDialog
          onClose={() => setCreating(false)}
          onSaved={(invoice) => {
            setCreating(false);
            setSelected(invoice);
          }}
        />
      )}
      {editing && (
        <InvoiceEditorDialog
          invoice={editing}
          onClose={() => setEditing(null)}
          onSaved={(invoice) => {
            setEditing(null);
            setSelected(invoice);
          }}
        />
      )}
      {selected && (
        <DocumentPreviewDialog
          document={selected}
          onClose={() => setSelected(null)}
          onEdit={(invoice) => {
            setSelected(null);
            setEditing(invoice);
          }}
          onOpenDocument={(document) => setSelected(document)}
        />
      )}
    </div>
  );
}
