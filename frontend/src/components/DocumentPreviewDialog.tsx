import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, getActiveCompanyId } from "../lib/api";
import { todayLocal } from "../lib/date";
import { apiErrorMessage } from "../lib/errors";
import {
  formatDate,
  formatDateTime,
  formatMoney,
  moneyProblem,
  statusBadgeClass,
  statusLabel,
  stripMoney,
} from "../lib/format";
import { safeStorage } from "../lib/safeStorage";
import { useModalKeys } from "../lib/useModalKeys";
import type { AuditAction, DocumentEvent, DocumentRecord } from "../types/api";
import AuditActionDialog from "./AuditActionDialog";

export default function DocumentPreviewDialog({
  document,
  onClose,
  onEdit,
  onOpenDocument,
}: {
  document: DocumentRecord;
  onClose: () => void;
  onEdit?: (invoice: DocumentRecord) => void;
  onOpenDocument?: (document: DocumentRecord) => void;
}) {
  const companyId = getActiveCompanyId();
  const queryClient = useQueryClient();
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [auditMode, setAuditMode] = useState<"void" | "restore" | null>(null);
  const [paying, setPaying] = useState(false);

  const isVoid = document.status === "void";
  const isInvoice = document.doc_type === "invoice";
  const label = isInvoice ? "Invoice" : "Receipt";
  const downloadUrl =
    companyId === null
      ? pdfUrl
      : `/api/v1/documents/${document.id}/pdf/download?company_id=${companyId}`;

  useEffect(() => {
    if (isVoid) return;
    let active = true;
    let url: string | null = null;
    api
      .get(`/documents/${document.id}/pdf`, {
        params: { inline: true },
        responseType: "blob",
      })
      .then((response) => {
        if (!active) return;
        url = URL.createObjectURL(response.data as Blob);
        setPdfUrl(url);
      })
      .catch((error) => active && setPdfError(apiErrorMessage(error)));
    return () => {
      // Blob URLs are process-wide allocations; release this one on unmount.
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [document.id, isVoid]);

  const audit = useQuery({
    queryKey: ["document-audit", companyId, document.id],
    queryFn: async () =>
      (await api.get<DocumentEvent[]>(`/documents/${document.id}/audit`)).data,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: ["document-audit", companyId, document.id] });
  };

  const voidMutation = useMutation({
    mutationFn: (action: AuditAction) =>
      api.delete(`/documents/${document.id}`, { data: action }),
    onSuccess: () => {
      refresh();
      setAuditMode(null);
      onClose();
    },
  });
  const restoreMutation = useMutation({
    mutationFn: (action: AuditAction) =>
      api.post(`/documents/${document.id}/restore`, action),
    onSuccess: () => {
      refresh();
      setAuditMode(null);
      onClose();
    },
  });

  useModalKeys({ open: !auditMode && !paying, onClose });
  const actionError = voidMutation.error ?? restoreMutation.error;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-2 sm:p-6"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-label={`${label} ${document.doc_number}`}
        className="card flex h-[min(880px,calc(100vh-16px))] w-[min(1000px,calc(100vw-16px))] flex-col sm:h-[min(880px,calc(100vh-48px))] sm:w-[min(1000px,calc(100vw-48px))]"
      >
        <header className="flex items-center justify-between gap-3 border-b px-5 py-3">
          <div className="min-w-0">
            <div className="text-xs text-slate-500">{label}</div>
            <div className="truncate font-mono text-lg font-semibold">{document.doc_number}</div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex h-8 items-center rounded px-3 text-xs leading-none ${statusBadgeClass(document.status)}`}
            >
              {statusLabel(document.status)}
            </span>
            {isInvoice && !isVoid && (
              <button
                className="inline-flex h-8 items-center rounded border border-slate-300 px-3 text-xs leading-none text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => onEdit?.(document)}
                disabled={!document.can_edit}
                title={document.edit_block_reason ?? undefined}
              >
                Edit
              </button>
            )}
            {isVoid ? (
              <button
                className="inline-flex h-8 items-center rounded border border-slate-300 px-3 text-xs leading-none text-slate-700 hover:bg-slate-100"
                onClick={() => setAuditMode("restore")}
              >
                Restore
              </button>
            ) : (
              <button
                className="inline-flex h-8 items-center rounded border border-rose-300 px-3 text-xs leading-none text-rose-700 hover:bg-rose-50"
                onClick={() => setAuditMode("void")}
              >
                Void
              </button>
            )}
            <button
              className="inline-flex h-8 w-8 items-center justify-center text-xl leading-none text-slate-500 hover:text-slate-900"
              onClick={onClose}
              aria-label={`Close ${label.toLowerCase()} preview`}
            >
              ×
            </button>
          </div>
        </header>

        <div className="grid grid-cols-2 gap-3 border-b px-5 py-3 text-sm sm:grid-cols-4">
          <Info label="Client">{document.customer_name}</Info>
          <Info label={isInvoice ? "Issued" : "Paid"}>
            {formatDate(isInvoice ? document.issue_date : document.paid_date)}
          </Info>
          <Info label={isInvoice ? "Due" : "Method"}>
            {isInvoice ? formatDate(document.due_date) : document.payment_method ?? "—"}
          </Info>
          <Info label="Total">{formatMoney(document.total)}</Info>
        </div>

        {isInvoice && !isVoid && (
          <div className="border-b px-5 py-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                <span className="text-slate-500">Received </span>
                <span className="font-medium tabular-nums">
                  {formatMoney(document.amount_received)}
                </span>
                <span className="text-slate-500"> of {formatMoney(document.total)}</span>
                {Number(document.amount_outstanding) > 0 && (
                  <span className="ml-2 text-amber-800">
                    {formatMoney(document.amount_outstanding)} outstanding
                  </span>
                )}
              </span>
              {Number(document.amount_outstanding) > 0 && (
                <button className="btn-primary" onClick={() => setPaying(true)}>
                  Record payment → Receipt
                </button>
              )}
            </div>
            {document.receipts.length > 0 && (
              <ul className="mt-2 space-y-1">
                {document.receipts.map((receipt) => (
                  <li key={receipt.id} className="flex items-center gap-2 text-xs">
                    <button
                      className="font-mono text-emerald-800 underline hover:text-emerald-900"
                      onClick={async () => {
                        const { data } = await api.get<DocumentRecord>(
                          `/documents/${receipt.id}`,
                        );
                        onOpenDocument?.(data);
                      }}
                    >
                      {receipt.doc_number}
                    </button>
                    <span className="tabular-nums">{formatMoney(receipt.total)}</span>
                    <span className="text-slate-500">{formatDate(receipt.paid_date)}</span>
                    {receipt.status === "void" && <span className="text-rose-700">void</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {!isInvoice && document.invoice_id && (
          <div className="border-b px-5 py-2 text-xs text-slate-600">
            Payment against{" "}
            <button
              className="font-mono text-emerald-800 underline hover:text-emerald-900"
              onClick={async () => {
                const { data } = await api.get<DocumentRecord>(
                  `/documents/${document.invoice_id}`,
                );
                onOpenDocument?.(data);
              }}
            >
              invoice #{document.invoice_id}
            </button>
          </div>
        )}

        {!!audit.data?.length && (
          <details className="border-b px-5 py-2 text-xs">
            <summary className="cursor-pointer text-slate-600">
              Audit history ({audit.data.length})
            </summary>
            <div className="mt-2 max-h-28 space-y-1 overflow-auto">
              {[...audit.data].reverse().map((event) => (
                <div key={event.id} className="border-b border-slate-100 pb-1">
                  <span className="font-medium">{event.action}</span> · {event.operator} ·{" "}
                  {formatDateTime(event.occurred_at)} — {event.reason}
                </div>
              ))}
            </div>
          </details>
        )}

        {actionError && (
          <div className="bg-rose-50 px-5 py-2 text-sm text-rose-700">
            {apiErrorMessage(actionError)}
          </div>
        )}

        <div className="flex-1 overflow-hidden bg-slate-100">
          {isVoid && (
            <div className="flex h-full items-center justify-center text-rose-700">
              Void documents cannot be rendered or downloaded.
            </div>
          )}
          {!isVoid && !pdfUrl && !pdfError && (
            <div className="flex h-full items-center justify-center text-slate-500">
              Rendering PDF…
            </div>
          )}
          {pdfError && (
            <div className="flex h-full items-center justify-center text-rose-700">{pdfError}</div>
          )}
          {pdfUrl && (
            <iframe className="h-full w-full border-0 bg-white" src={pdfUrl} title={document.doc_number} />
          )}
        </div>

        {pdfUrl && downloadUrl && (
          <footer className="flex justify-end border-t px-5 py-3">
            <a className="btn-secondary" href={downloadUrl}>
              Download PDF
            </a>
          </footer>
        )}
      </div>

      {paying && (
        <RecordPaymentDialog
          invoice={document}
          onClose={() => setPaying(false)}
          onCreated={(receipt) => {
            setPaying(false);
            refresh();
            onOpenDocument?.(receipt);
          }}
        />
      )}

      {auditMode && (
        <AuditActionDialog
          title={`${auditMode === "void" ? "Void" : "Restore"} ${label}`}
          message={
            auditMode === "void"
              ? isInvoice
                ? "The PDF is kept but access is blocked, and every receipt on this invoice is voided with it. This is recorded."
                : "The PDF is kept but access is blocked, and the invoice balance reopens. This is recorded."
              : "Restoring is recorded and all integrity checks run again."
          }
          confirmLabel={auditMode === "void" ? "Void document" : "Restore document"}
          pending={voidMutation.isPending || restoreMutation.isPending}
          error={actionError ? apiErrorMessage(actionError) : null}
          onClose={() => setAuditMode(null)}
          onConfirm={(action) =>
            auditMode === "void" ? voidMutation.mutate(action) : restoreMutation.mutate(action)
          }
        />
      )}
    </div>
  );
}

function Info({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="truncate">{children}</div>
    </div>
  );
}

function RecordPaymentDialog({
  invoice,
  onClose,
  onCreated,
}: {
  invoice: DocumentRecord;
  onClose: () => void;
  onCreated: (receipt: DocumentRecord) => void;
}) {
  const outstanding = invoice.amount_outstanding ?? "0";
  const [amount, setAmount] = useState(outstanding);
  const [paidDate, setPaidDate] = useState(todayLocal());
  const [method, setMethod] = useState("Bank transfer");
  const [operator, setOperator] = useState(
    () => safeStorage.getItem("invoice-receipt.operator") ?? "",
  );

  const mutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<DocumentRecord>(`/invoices/${invoice.id}/receipts`, {
        amount: stripMoney(amount),
        paid_date: paidDate,
        payment_method: method.trim(),
        operator: operator.trim(),
      });
      return data;
    },
    onSuccess: (receipt) => {
      safeStorage.setItem("invoice-receipt.operator", operator.trim());
      onCreated(receipt);
    },
  });

  const amountIssue = moneyProblem(amount);
  const problems = [
    amountIssue ? `Amount ${amountIssue}.` : null,
    !amountIssue && Number(stripMoney(amount)) <= 0 ? "Amount must be above zero." : null,
    !amountIssue && Number(stripMoney(amount)) > Number(outstanding)
      ? `Amount cannot exceed the ${formatMoney(outstanding)} outstanding.`
      : null,
    paidDate ? null : "Enter the payment date.",
    paidDate && paidDate > todayLocal() ? "The payment date cannot be in the future." : null,
    paidDate && paidDate < invoice.issue_date
      ? `The payment date cannot be before the invoice date (${formatDate(invoice.issue_date)}).`
      : null,
    method.trim() ? null : "Enter the payment method.",
    operator.trim() ? null : "Enter who is recording this.",
  ].filter((problem): problem is string => !!problem);

  const submit = () => {
    if (!problems.length && !mutation.isPending) mutation.mutate();
  };
  useModalKeys({ open: true, onClose, onSubmit: submit });

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-3">
      <div
        role="dialog"
        aria-label="Record payment"
        className="card w-[min(460px,calc(100vw-24px))] max-h-[calc(100vh-24px)] overflow-y-auto p-5"
      >
        <h3 className="font-semibold">Record payment</h3>
        <p className="mb-4 mt-1 text-sm text-slate-600">
          Creates a receipt against {invoice.doc_number}. {formatMoney(outstanding)} outstanding.
        </p>
        <label className="mb-3 block text-sm">
          <span className="mb-1 block text-slate-600">Amount received *</span>
          <input
            className="input text-right"
            inputMode="decimal"
            value={amount}
            aria-invalid={!!amountIssue || undefined}
            onChange={(event) => {
              setAmount(event.target.value);
              mutation.reset();
            }}
          />
        </label>
        <label className="mb-3 block text-sm">
          <span className="mb-1 block text-slate-600">Payment date *</span>
          <input
            type="date"
            className="input"
            min={invoice.issue_date}
            max={todayLocal()}
            value={paidDate}
            onChange={(event) => {
              setPaidDate(event.target.value);
              mutation.reset();
            }}
          />
        </label>
        <label className="mb-3 block text-sm">
          <span className="mb-1 block text-slate-600">Payment method *</span>
          <input
            className="input"
            value={method}
            onChange={(event) => {
              setMethod(event.target.value);
              mutation.reset();
            }}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">Operator *</span>
          <input
            className="input"
            value={operator}
            onChange={(event) => setOperator(event.target.value)}
          />
        </label>
        {mutation.isError && (
          <p className="mt-3 text-sm text-rose-700">{apiErrorMessage(mutation.error)}</p>
        )}
        {problems.length > 0 && (
          <ul className="mt-3 space-y-1 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </button>
          <button
            className="btn-primary"
            onClick={submit}
            disabled={problems.length > 0 || mutation.isPending}
          >
            {mutation.isPending ? "Creating…" : "Create receipt"}
          </button>
        </div>
      </div>
    </div>
  );
}
