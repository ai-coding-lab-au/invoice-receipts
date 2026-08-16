import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, getActiveCompanyId } from "../lib/api";
import { apiErrorMessage } from "../lib/errors";
import { formatDateTime } from "../lib/format";
import type { Company } from "../types/api";

type Editable = Omit<Company, "id" | "updated_at">;

const SECTIONS: { title: string; hint?: string; fields: [keyof Editable, string][] }[] = [
  {
    title: "Business",
    fields: [
      ["legal_name", "Legal name *"],
      ["trading_name", "Business name (optional)"],
      ["abn", "ABN"],
      ["phone", "Phone"],
      ["email", "Email"],
    ],
  },
  {
    title: "Address",
    fields: [
      ["address_line1", "Address line 1"],
      ["address_line2", "Address line 2"],
      ["suburb", "Suburb"],
      ["state", "State"],
      ["postcode", "Postcode"],
    ],
  },
  {
    title: "Bank details",
    hint: "Printed on invoices so clients know where to pay.",
    fields: [
      ["bank_account_name", "Account name"],
      ["bank_name", "Bank"],
      ["bank_bsb", "BSB"],
      ["bank_account_number", "Account number"],
      ["bank_swift", "SWIFT (international)"],
    ],
  },
];

export default function SettingsPage() {
  const companyId = getActiveCompanyId();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Partial<Editable>>({});
  const [saved, setSaved] = useState(false);

  const query = useQuery({
    queryKey: ["company", companyId],
    queryFn: async () => (await api.get<Company>("/company")).data,
  });

  const mutation = useMutation({
    mutationFn: async (payload: Partial<Editable>) =>
      (await api.patch<Company>("/company", payload)).data,
    onSuccess: () => {
      setForm({});
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["company", companyId] });
    },
  });

  if (query.isLoading) return <p className="text-sm text-slate-500">Loading…</p>;
  if (query.isError || !query.data) {
    return <p className="text-sm text-rose-700">Unable to load settings.</p>;
  }

  const merged = { ...query.data, ...form } as Company;
  const dirty = Object.keys(form).length > 0;
  const legalNameMissing = !merged.legal_name.trim();

  const set = (key: keyof Editable, value: string | boolean | number | null) => {
    setSaved(false);
    mutation.reset();
    setForm((current) => ({ ...current, [key]: value }));
  };

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="mt-1 text-xs text-slate-500">
          These details are copied onto each document when it is issued. Changing them here
          never rewrites a document that has already been sent.
        </p>
      </header>

      {SECTIONS.map((section) => (
        <section key={section.title} className="card p-4">
          <h2 className="text-sm font-semibold">{section.title}</h2>
          {section.hint && <p className="mt-1 text-xs text-slate-500">{section.hint}</p>}
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {section.fields.map(([key, label]) => (
              <label key={key} className="block text-sm">
                <span className="mb-1 block text-slate-600">{label}</span>
                <input
                  className="input"
                  placeholder={key === "abn" ? "e.g. 51 824 753 556" : undefined}
                  value={(merged[key] as string | null) ?? ""}
                  required={key === "legal_name"}
                  onChange={(event) =>
                    set(key, key === "legal_name" ? event.target.value : event.target.value || null)
                  }
                />
                {key === "legal_name" && legalNameMissing && (
                  <span className="mt-1 block text-xs text-rose-700">
                    Legal name is required; business name is optional.
                  </span>
                )}
              </label>
            ))}
          </div>
        </section>
      ))}

      <section className="card p-4">
        <h2 className="text-sm font-semibold">Tax and terms</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={merged.gst_registered}
              onChange={(event) => set("gst_registered", event.target.checked)}
            />
            Registered for GST (choose GST or GST-free on each invoice line)
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-600">Default payment terms (days)</span>
            <input
              type="number"
              min={0}
              max={365}
              className="input"
              value={merged.payment_terms_days}
              onChange={(event) => set("payment_terms_days", Number(event.target.value))}
            />
          </label>
        </div>
        {merged.gst_registered && !merged.abn && (
          <p className="mt-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            A GST-registered business needs a valid ABN before any document can be issued.
          </p>
        )}
      </section>

      <div className="flex items-center gap-3">
        <button
          className="btn-primary"
          disabled={!dirty || mutation.isPending || legalNameMissing}
          onClick={() => mutation.mutate(form)}
        >
          {mutation.isPending ? "Saving…" : "Save changes"}
        </button>
        {dirty && !mutation.isPending && (
          <button className="btn-secondary" onClick={() => setForm({})}>
            Discard
          </button>
        )}
        {mutation.isError && (
          <span className="text-sm text-rose-700">{apiErrorMessage(mutation.error)}</span>
        )}
        {saved && !dirty && <span className="text-sm text-emerald-800">Saved.</span>}
        <span className="ml-auto text-xs text-slate-500">
          Last updated {formatDateTime(query.data.updated_at)}
        </span>
      </div>
    </div>
  );
}
