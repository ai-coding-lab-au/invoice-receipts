import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, getActiveCompanyId } from "../lib/api";
import { todayLocal, addDaysIso } from "../lib/date";
import { apiErrorMessage } from "../lib/errors";
import { formatMoney, moneyProblem, stripMoney } from "../lib/format";
import { safeStorage } from "../lib/safeStorage";
import { useModalKeys } from "../lib/useModalKeys";
import { ClientDialog } from "../pages/Clients";
import type { Client, Company, DocumentRecord, InvoiceLineInput } from "../types/api";

const emptyLine = (): InvoiceLineInput => ({
  description: "",
  quantity: "1",
  unit_price: "0.00",
  gst_treatment: "taxable",
});

const roundCents = (value: number) => Math.round((value + Number.EPSILON) * 100) / 100;

export default function InvoiceEditorDialog({
  invoice,
  onClose,
  onSaved,
}: {
  /** Editing an existing invoice, or undefined to create a new one. */
  invoice?: DocumentRecord;
  onClose: () => void;
  onSaved: (invoice: DocumentRecord) => void;
}) {
  const companyId = getActiveCompanyId();
  const queryClient = useQueryClient();
  const editing = !!invoice;
  const dialogRef = useRef<HTMLDivElement>(null);
  const clientSelectRef = useRef<HTMLSelectElement>(null);

  const [clientId, setClientId] = useState(String(invoice?.client_id ?? ""));
  const [addingClient, setAddingClient] = useState(false);
  const [issueDate, setIssueDate] = useState(invoice?.issue_date ?? todayLocal());
  const [dueDate, setDueDate] = useState(invoice?.due_date ?? "");
  const [dueTouched, setDueTouched] = useState(!!invoice?.due_date);
  const [gstInclusive, setGstInclusive] = useState(invoice?.gst_inclusive ?? false);
  const [notes, setNotes] = useState(invoice?.notes ?? "");
  const [operator, setOperator] = useState(
    () => safeStorage.getItem("invoice-receipt.operator") ?? "",
  );
  const [showProblems, setShowProblems] = useState(false);
  const [lines, setLines] = useState<InvoiceLineInput[]>(() =>
    invoice
      ? invoice.lines.map((line) => ({
          description: line.description,
          quantity: String(Number(line.quantity)),
          unit_price: line.unit_price,
          gst_treatment: line.gst_treatment,
        }))
      : [emptyLine()],
  );

  const company = useQuery({
    queryKey: ["company", companyId],
    queryFn: async () => (await api.get<Company>("/company")).data,
  });
  const clients = useQuery({
    queryKey: ["clients", companyId, "picker"],
    queryFn: async () =>
      (await api.get<Client[]>("/clients", { params: { active_only: true } })).data,
  });

  const gstRegistered = company.data?.gst_registered ?? false;
  const terms = company.data?.payment_terms_days ?? 14;
  const effectiveDue = dueTouched && dueDate ? dueDate : addDaysIso(issueDate, terms);

  const updateLine = (index: number, patch: Partial<InvoiceLineInput>) =>
    setLines((current) =>
      current.map((line, i) => (i === index ? { ...line, ...patch } : line)),
    );

  // Every amount must parse before a total can be shown. Displaying a figure
  // that silently skips an unparseable row would not match the issued invoice.
  const lineProblems = useMemo(
    () =>
      lines.flatMap((line, index) => {
        const row = index + 1;
        const found: string[] = [];
        if (!line.description.trim()) found.push(`Line ${row} needs a description.`);
        const qty = moneyProblem(line.quantity);
        if (qty || Number(stripMoney(line.quantity)) <= 0) {
          found.push(`Line ${row} quantity must be a number above zero.`);
        }
        const price = moneyProblem(line.unit_price);
        if (price) found.push(`Line ${row} unit price ${price}.`);
        return found;
      }),
    [lines],
  );

  const totals = useMemo(() => {
    if (lineProblems.length) return null;
    const amounts = lines.map((line) => ({
      amount: roundCents(
        Number(stripMoney(line.quantity)) * Number(stripMoney(line.unit_price)),
      ),
      taxable: line.gst_treatment === "taxable",
    }));
    const gross = roundCents(amounts.reduce((sum, line) => sum + line.amount, 0));
    if (!gstRegistered) return { subtotal: gross, gst: 0, total: gross };
    const taxable = roundCents(
      amounts.reduce((sum, line) => sum + (line.taxable ? line.amount : 0), 0),
    );
    if (gstInclusive) {
      const taxableSubtotal = roundCents(taxable / 1.1);
      const gst = roundCents(taxable - taxableSubtotal);
      return { subtotal: roundCents(gross - gst), gst, total: gross };
    }
    const gst = roundCents(taxable * 0.1);
    return { subtotal: gross, gst, total: roundCents(gross + gst) };
  }, [lines, lineProblems.length, gstRegistered, gstInclusive]);

  const problems = [
    Number(clientId) > 0 ? null : "Choose a client.",
    issueDate ? null : "Enter the invoice date.",
    issueDate && issueDate > todayLocal() ? "The invoice date cannot be in the future." : null,
    dueTouched && dueDate && dueDate < issueDate
      ? "The due date cannot be before the invoice date."
      : null,
    ...lineProblems,
  ].filter((problem): problem is string => !!problem);

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = {
        client_id: Number(clientId),
        issue_date: issueDate,
        due_date: dueTouched && dueDate ? dueDate : null,
        lines: lines.map((line) => ({
          description: line.description.trim(),
          quantity: stripMoney(line.quantity),
          unit_price: stripMoney(line.unit_price),
          gst_treatment: line.gst_treatment,
        })),
        gst_inclusive: gstInclusive,
        notes: notes.trim() || null,
        operator: operator.trim() || null,
      };
      const { data } = editing
        ? await api.put<DocumentRecord>(`/invoices/${invoice!.id}`, payload)
        : await api.post<DocumentRecord>("/invoices", payload);
      return data;
    },
    onSuccess: (saved) => {
      const cleanedOperator = operator.trim();
      if (cleanedOperator) {
        safeStorage.setItem("invoice-receipt.operator", cleanedOperator);
      } else {
        safeStorage.removeItem("invoice-receipt.operator");
      }
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      onSaved(saved);
    },
  });

  const submit = () => {
    if (problems.length) {
      setShowProblems(true);
      window.requestAnimationFrame(() => {
        const firstInvalid = dialogRef.current?.querySelector<HTMLElement>(
          '[aria-invalid="true"]',
        );
        firstInvalid?.scrollIntoView({ behavior: "smooth", block: "center" });
        firstInvalid?.focus({ preventScroll: true });
      });
      return;
    }
    if (!mutation.isPending) mutation.mutate();
  };
  useModalKeys({ open: !addingClient, onClose });

  const closeClientDialog = () => {
    setAddingClient(false);
    window.requestAnimationFrame(() => clientSelectRef.current?.focus());
  };

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (addingClient) {
      dialog.setAttribute("inert", "");
    } else {
      dialog.removeAttribute("inert");
    }
    return () => dialog.removeAttribute("inert");
  }, [addingClient]);

  const validationMessage =
    showProblems && problems.length > 0
      ? problems.length === 1
        ? problems[0]
        : problems.join(" ")
      : null;
  const submitError = mutation.isError ? apiErrorMessage(mutation.error) : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-2 sm:p-5"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-label={editing ? `Edit ${invoice!.doc_number}` : "New invoice"}
        aria-modal={!addingClient}
        aria-hidden={addingClient || undefined}
        className="card flex max-h-[calc(100dvh-16px)] w-[min(960px,calc(100vw-16px))] flex-col overflow-hidden shadow-2xl shadow-slate-950/20 sm:max-h-[calc(100dvh-40px)] sm:w-[min(960px,calc(100vw-40px))]"
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3 sm:px-6">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-slate-900">
              {editing ? `Edit ${invoice!.doc_number}` : "New invoice"}
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">Fields marked * are required.</p>
          </div>
          <button
            className="inline-flex h-8 w-8 items-center justify-center rounded text-xl leading-none text-slate-500 hover:bg-slate-100 hover:text-slate-900 active:scale-[0.98]"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4 sm:px-6">
          <section className="grid gap-3 rounded-lg border border-slate-200 bg-slate-50/80 p-3 sm:grid-cols-3 sm:p-4">
            <div className="block text-sm">
              <div className="mb-1 flex items-center justify-between gap-2">
                <label className="font-medium text-slate-700" htmlFor="invoice-client">
                  Client *
                </label>
                <button
                  type="button"
                  className="inline-flex h-[30px] shrink-0 items-center justify-center rounded border border-emerald-300 bg-emerald-50 px-2.5 text-xs font-semibold text-emerald-900 shadow-sm transition-colors hover:border-emerald-400 hover:bg-emerald-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 active:scale-[0.98]"
                  onClick={() => setAddingClient(true)}
                >
                  + New client
                </button>
              </div>
              <select
                ref={clientSelectRef}
                id="invoice-client"
                className="input"
                aria-invalid={showProblems && Number(clientId) <= 0}
                value={clientId}
                onChange={(event) => setClientId(event.target.value)}
              >
                <option value="">Select a client…</option>
                {(clients.data ?? []).map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.display_name}
                  </option>
                ))}
              </select>
            </div>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">Invoice date *</span>
              <input
                type="date"
                className="input"
                aria-invalid={showProblems && (!issueDate || issueDate > todayLocal())}
                max={todayLocal()}
                value={issueDate}
                onChange={(event) => setIssueDate(event.target.value)}
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                Due date{!dueTouched && <span className="text-slate-400"> (auto)</span>}
              </span>
              <input
                type="date"
                className="input"
                aria-invalid={showProblems && !!dueDate && dueDate < issueDate}
                min={issueDate}
                value={dueTouched ? dueDate : effectiveDue}
                onChange={(event) => {
                  setDueTouched(true);
                  setDueDate(event.target.value);
                }}
              />
            </label>
          </section>

          {clients.data && clients.data.length === 0 && (
            <p
              className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
              role="status"
            >
              No active clients yet. Use New client above to add one without leaving this invoice.
            </p>
          )}

          <section aria-labelledby="invoice-lines-heading">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 id="invoice-lines-heading" className="text-sm font-semibold text-slate-900">
                  Line items
                </h3>
                <p className="mt-0.5 text-xs text-slate-500">
                  Add each product or service as a separate line
                  {gstRegistered ? " and choose its GST treatment." : "."}
                </p>
              </div>
              <button
                className="btn-secondary shrink-0 active:scale-[0.98]"
                onClick={() => setLines((current) => [...current, emptyLine()])}
              >
                + Add line
              </button>
            </div>
            <div
              className={`mb-1 hidden gap-2 px-2 text-[11px] font-medium uppercase tracking-wide text-slate-500 sm:grid ${
                gstRegistered
                  ? "sm:grid-cols-[minmax(0,1fr)_88px_72px_104px_96px_32px]"
                  : "sm:grid-cols-[minmax(0,1fr)_76px_112px_104px_32px]"
              }`}
            >
              <span>Description *</span>
              {gstRegistered && <span>Tax</span>}
              <span className="text-right">Qty</span>
              <span className="text-right">Unit price</span>
              <span className="text-right">Amount</span>
              <span />
            </div>
            <div className="space-y-2">
              {lines.map((line, index) => (
                <div
                  key={index}
                  className={`grid grid-cols-[minmax(0,1fr)_72px_104px_32px] gap-2 rounded-lg border border-slate-200 bg-white p-2 sm:border-0 sm:p-0 ${
                    gstRegistered
                      ? "sm:grid-cols-[minmax(0,1fr)_88px_72px_104px_96px_32px]"
                      : "sm:grid-cols-[minmax(0,1fr)_76px_112px_104px_32px]"
                  }`}
                >
                  <input
                    className="input col-span-full sm:col-span-1"
                    placeholder="Description *"
                    aria-label={`Line ${index + 1} description`}
                    aria-invalid={showProblems && !line.description.trim()}
                    value={line.description}
                    onChange={(event) => updateLine(index, { description: event.target.value })}
                  />
                  {gstRegistered && (
                    <select
                      className="input col-span-2 sm:col-span-1"
                      aria-label={`Line ${index + 1} GST treatment`}
                      value={line.gst_treatment}
                      onChange={(event) =>
                        updateLine(index, {
                          gst_treatment: event.target.value as InvoiceLineInput["gst_treatment"],
                        })
                      }
                    >
                      <option value="taxable">GST 10%</option>
                      <option value="gst_free">GST-free</option>
                    </select>
                  )}
                  <input
                    className="input text-right"
                    inputMode="decimal"
                    placeholder="Qty"
                    aria-label={`Line ${index + 1} quantity`}
                    aria-invalid={
                      showProblems &&
                      (!!moneyProblem(line.quantity) || Number(stripMoney(line.quantity)) <= 0)
                    }
                    value={line.quantity}
                    onChange={(event) => updateLine(index, { quantity: event.target.value })}
                  />
                  <input
                    className="input text-right"
                    inputMode="decimal"
                    placeholder="Unit price"
                    aria-label={`Line ${index + 1} unit price`}
                    aria-invalid={showProblems && !!moneyProblem(line.unit_price)}
                    value={line.unit_price}
                    onChange={(event) => updateLine(index, { unit_price: event.target.value })}
                  />
                  <div className="flex h-[34px] items-center justify-end rounded bg-slate-50 px-2 text-sm font-medium tabular-nums text-slate-700 sm:bg-transparent sm:px-0">
                    {moneyProblem(line.quantity) || moneyProblem(line.unit_price)
                      ? "–"
                      : formatMoney(
                          Number(stripMoney(line.quantity)) * Number(stripMoney(line.unit_price)),
                        )}
                  </div>
                  <button
                    className="h-[34px] rounded text-slate-400 hover:bg-rose-50 hover:text-rose-700 active:scale-[0.98]"
                    aria-label={`Remove line ${index + 1}`}
                    onClick={() =>
                      setLines((current) =>
                        current.length === 1 ? [emptyLine()] : current.filter((_, i) => i !== index),
                      )
                    }
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          </section>

          <section className="grid gap-4 border-t border-slate-200 pt-4 md:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
            <div className="space-y-3">
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-slate-700">
                  Notes <span className="font-normal text-slate-400">(printed on the invoice)</span>
                </span>
                <textarea
                  className="input min-h-[88px] resize-y"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-slate-700">Operator</span>
                <input
                  className="input"
                  value={operator}
                  onChange={(event) => setOperator(event.target.value)}
                  placeholder="Person issuing this invoice"
                />
              </label>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              {gstRegistered && (
                <label className="mb-3 flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={gstInclusive}
                    onChange={(event) => setGstInclusive(event.target.checked)}
                  />
                  Taxable line prices already include GST
                </label>
              )}
              <div className="space-y-1 text-sm">
                <Row label="Subtotal" value={totals ? formatMoney(totals.subtotal) : "–"} />
                {gstRegistered && (
                  <Row label="GST (10%)" value={totals ? formatMoney(totals.gst) : "–"} />
                )}
                <div className="mt-3 border-t border-slate-200 pt-3">
                  <Row
                    label="Total"
                    value={totals ? formatMoney(totals.total) : "–"}
                    strong
                  />
                </div>
              </div>
            </div>
          </section>

        </div>

        {(validationMessage || submitError) && (
          <div
            id="invoice-submit-feedback"
            className={`border-t px-4 py-2.5 text-sm sm:px-6 ${
              submitError
                ? "border-rose-200 bg-rose-50 text-rose-800"
                : "border-amber-200 bg-amber-50 text-amber-900"
            }`}
            role="alert"
            aria-live="assertive"
          >
            <span className="font-semibold">
              {submitError
                ? editing
                  ? "Unable to save changes. "
                  : "Unable to issue invoice. "
                : editing
                  ? "Check the invoice before saving. "
                  : "Check the invoice before issuing. "}
            </span>
            {submitError ?? validationMessage}
          </div>
        )}

        <footer className="flex flex-wrap items-center gap-3 border-t border-slate-200 bg-white px-4 py-3 sm:px-6">
          <div className="min-w-0 flex-1 text-xs" aria-live="polite">
            <p className="text-slate-500">
              {lines.length} line{lines.length === 1 ? "" : "s"}
              {totals ? ` · ${formatMoney(totals.total)} total` : ""}
            </p>
          </div>
          <div className="ml-auto flex gap-2">
            <button
              className="btn-secondary active:scale-[0.98]"
              onClick={onClose}
              disabled={mutation.isPending}
            >
              Cancel
            </button>
            <button
              className="btn-primary min-w-[112px] active:scale-[0.98]"
              onClick={submit}
              disabled={mutation.isPending}
              aria-describedby={validationMessage || submitError ? "invoice-submit-feedback" : undefined}
            >
              {mutation.isPending ? "Saving…" : editing ? "Save changes" : "Issue invoice"}
            </button>
          </div>
        </footer>
      </div>
      {addingClient && (
        <ClientDialog
          client={null}
          onClose={closeClientDialog}
          onSaved={(saved) => {
            queryClient.setQueryData<Client[]>(
              ["clients", companyId, "picker"],
              (current) =>
                [...(current ?? []).filter((client) => client.id !== saved.id), saved].sort(
                  (left, right) => left.display_name.localeCompare(right.display_name),
                ),
            );
            setClientId(String(saved.id));
          }}
        />
      )}
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div
      className={`flex items-baseline justify-between gap-4 ${
        strong ? "text-base font-semibold text-slate-900" : ""
      }`}
    >
      <span className={strong ? "" : "text-slate-500"}>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}
