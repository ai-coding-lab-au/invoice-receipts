import { useState } from "react";

import { safeStorage } from "../lib/safeStorage";
import { useModalKeys } from "../lib/useModalKeys";
import type { AuditAction } from "../types/api";

export default function AuditActionDialog({
  title,
  message,
  confirmLabel,
  pending,
  error,
  onClose,
  onConfirm,
}: {
  title: string;
  message: string;
  confirmLabel: string;
  pending: boolean;
  error?: string | null;
  onClose: () => void;
  onConfirm: (action: AuditAction) => void;
}) {
  const [operator, setOperator] = useState(
    () => safeStorage.getItem("invoice-receipt.operator") ?? "",
  );
  const [reason, setReason] = useState("");

  // Mirrors the server rule exactly, so the button is never enabled for
  // something the API will reject.
  const problems = [
    operator.trim() ? null : "Enter who is doing this.",
    reason.trim().length >= 3 ? null : "Give a reason of at least 3 characters.",
  ].filter((problem): problem is string => !!problem);

  const submit = () => {
    if (problems.length || pending) return;
    const action = { operator: operator.trim(), reason: reason.trim() };
    safeStorage.setItem("invoice-receipt.operator", action.operator);
    onConfirm(action);
  };
  useModalKeys({ open: true, onClose, onSubmit: submit });

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-3">
      <div
        role="dialog"
        aria-label={title}
        className="card w-[min(440px,calc(100vw-24px))] max-h-[calc(100vh-24px)] overflow-y-auto p-5 shadow-xl"
      >
        <h3 className="font-semibold">{title}</h3>
        <p className="mb-4 mt-1 text-sm text-slate-600">{message}</p>
        <label className="mb-3 block text-sm">
          <span className="mb-1 block text-slate-600">Operator</span>
          <input
            className="input"
            value={operator}
            onChange={(event) => setOperator(event.target.value)}
            autoFocus
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">Reason</span>
          <textarea
            className="input min-h-20"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        {error && <p className="mt-3 text-sm text-rose-700">{error}</p>}
        {problems.length > 0 && (
          <ul className="mt-3 space-y-1 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose} disabled={pending}>
            Cancel
          </button>
          <button
            className="btn-primary"
            onClick={submit}
            disabled={problems.length > 0 || pending}
          >
            {pending ? "Saving…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
