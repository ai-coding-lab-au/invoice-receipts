import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, getActiveCompanyId, limitedList } from "../lib/api";
import { apiErrorMessage } from "../lib/errors";
import { useModalKeys } from "../lib/useModalKeys";
import type { Client } from "../types/api";

type Draft = {
  display_name: string;
  abn: string;
  email: string;
  phone: string;
  address: string;
  notes: string;
};

const emptyDraft = (): Draft => ({
  display_name: "",
  abn: "",
  email: "",
  phone: "",
  address: "",
  notes: "",
});

export default function ClientsPage() {
  const companyId = getActiveCompanyId();
  const [q, setQ] = useState("");
  const [activeOnly, setActiveOnly] = useState(true);
  const [editing, setEditing] = useState<Client | "new" | null>(null);

  const query = useQuery({
    queryKey: ["clients", companyId, q, activeOnly],
    queryFn: async () =>
      limitedList(
        await api.get<Client[]>("/clients", {
          params: { q: q.trim() || undefined, active_only: activeOnly },
        }),
      ),
  });

  const filtered = q.trim() !== "" || !activeOnly;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Clients</h1>
          <p className="mt-1 text-xs text-slate-500">
            Details are copied onto an invoice when it is issued, so editing a client never
            changes a document already sent.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setEditing("new")}>
          + New client
        </button>
      </header>

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b p-4">
          <input
            className="input w-64"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search name…"
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(event) => setActiveOnly(event.target.checked)}
            />
            Active only
          </label>
        </div>

        <div className="border-b bg-slate-50 px-4 py-2.5 text-sm">
          <strong>{query.data?.total ?? 0}</strong>{" "}
          {(query.data?.total ?? 0) === 1 ? "client" : "clients"}
        </div>

        {query.isLoading && <p className="px-4 py-10 text-sm text-slate-500">Loading…</p>}
        {query.isError && (
          <p className="px-4 py-10 text-sm text-rose-700">Unable to load clients.</p>
        )}
        {query.data?.items.length === 0 && (
          <p className="px-4 py-12 text-center text-sm text-slate-500">
            {filtered
              ? "No clients match the current search or filter."
              : "No clients yet. Click + New client to add the first one."}
          </p>
        )}

        {!!query.data?.items.length && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-600">
                <tr>
                  <th className="px-4 py-2">Name</th>
                  <th className="px-4 py-2">ABN</th>
                  <th className="px-4 py-2">Email</th>
                  <th className="px-4 py-2">Phone</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((client) => (
                  <tr key={client.id} className="border-t">
                    <td className="px-4 py-2 font-medium">
                      {client.display_name}
                      {!client.is_active && (
                        <span className="ml-2 text-xs text-rose-700">Inactive</span>
                      )}
                    </td>
                    <td className="px-4 py-2">{client.abn ?? "—"}</td>
                    <td className="px-4 py-2">{client.email ?? "—"}</td>
                    <td className="px-4 py-2">{client.phone ?? "—"}</td>
                    <td className="px-4 py-2 text-right">
                      <button
                        className="text-sm text-emerald-800 underline hover:text-emerald-900"
                        onClick={() => setEditing(client)}
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {editing && (
        <ClientDialog
          client={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

export function ClientDialog({
  client,
  onClose,
  onSaved,
}: {
  client: Client | null;
  onClose: () => void;
  onSaved?: (client: Client) => void;
}) {
  const queryClient = useQueryClient();
  const dialogRef = useRef<HTMLDivElement>(null);
  const mutationPendingRef = useRef(false);
  const [draft, setDraft] = useState<Draft>(() =>
    client
      ? {
          display_name: client.display_name,
          abn: client.abn ?? "",
          email: client.email ?? "",
          phone: client.phone ?? "",
          address: client.address ?? "",
          notes: client.notes ?? "",
        }
      : emptyDraft(),
  );
  const [isActive, setIsActive] = useState(client?.is_active ?? true);

  const set = (patch: Partial<Draft>) => setDraft((current) => ({ ...current, ...patch }));

  const mutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        display_name: draft.display_name.trim(),
        abn: draft.abn.trim() || null,
        email: draft.email.trim() || null,
        phone: draft.phone.trim() || null,
        address: draft.address.trim() || null,
        notes: draft.notes.trim() || null,
      };
      if (client) {
        body.is_active = isActive;
        return (await api.patch<Client>(`/clients/${client.id}`, body)).data;
      }
      return (await api.post<Client>("/clients", body)).data;
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      onSaved?.(saved);
      onClose();
    },
  });

  const problems = [draft.display_name.trim() ? null : "Enter the client name."].filter(
    (problem): problem is string => !!problem,
  );

  const submit = () => {
    if (!problems.length && !mutation.isPending) mutation.mutate();
  };
  mutationPendingRef.current = mutation.isPending;
  const requestClose = () => {
    if (!mutationPendingRef.current) onClose();
  };
  useModalKeys({ open: true, onClose: requestClose, onSubmit: submit, containerRef: dialogRef });

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-3">
      <div
        ref={dialogRef}
        role="dialog"
        aria-label={client ? `Edit ${client.display_name}` : "New client"}
        aria-modal="true"
        tabIndex={-1}
        className="card w-[min(520px,calc(100vw-24px))] max-h-[calc(100vh-24px)] overflow-y-auto p-5"
      >
        <h3 className="font-semibold">{client ? "Edit client" : "New client"}</h3>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Name *" wide>
            <input
              className="input"
              value={draft.display_name}
              onChange={(event) => set({ display_name: event.target.value })}
              autoFocus
            />
          </Field>
          <Field label="ABN">
            <input
              className="input"
              placeholder="e.g. 12 345 678 901"
              value={draft.abn}
              onChange={(event) => set({ abn: event.target.value })}
            />
          </Field>
          <Field label="Phone">
            <input
              className="input"
              value={draft.phone}
              onChange={(event) => set({ phone: event.target.value })}
            />
          </Field>
          <Field label="Email" wide>
            <input
              className="input"
              value={draft.email}
              onChange={(event) => set({ email: event.target.value })}
            />
          </Field>
          <Field label="Address" wide>
            <textarea
              className="input min-h-[60px]"
              value={draft.address}
              onChange={(event) => set({ address: event.target.value })}
            />
          </Field>
          <Field label="Notes (not printed)" wide>
            <textarea
              className="input min-h-[48px]"
              value={draft.notes}
              onChange={(event) => set({ notes: event.target.value })}
            />
          </Field>
        </div>
        {client && (
          <label className="mt-3 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(event) => setIsActive(event.target.checked)}
            />
            Active (available when issuing an invoice)
          </label>
        )}
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
          <button className="btn-secondary" onClick={requestClose} disabled={mutation.isPending}>
            Cancel
          </button>
          <button
            className="btn-primary"
            onClick={submit}
            disabled={problems.length > 0 || mutation.isPending}
          >
            {mutation.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  wide,
  children,
}: {
  label: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className={`block text-sm ${wide ? "sm:col-span-2" : ""}`}>
      <span className="mb-1 block text-slate-600">{label}</span>
      {children}
    </label>
  );
}
