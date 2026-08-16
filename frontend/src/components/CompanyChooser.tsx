import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { api } from "../lib/api";
import { apiErrorMessage } from "../lib/errors";
import type { Company } from "../types/api";

function displayName(company: Company): string {
  return company.trading_name || company.legal_name;
}

function monogram(company: Company): string {
  return displayName(company)
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join("");
}

export default function CompanyChooser({
  companies,
  onSelect,
  onCreated,
}: {
  companies: Company[];
  onSelect: (company: Company) => void;
  onCreated: (company: Company) => void;
}) {
  const [legalName, setLegalName] = useState("");
  const [tradingName, setTradingName] = useState("");

  const create = useMutation({
    mutationFn: async () =>
      (
        await api.post<Company>("/companies", {
          legal_name: legalName.trim(),
          trading_name: tradingName.trim() || null,
        })
      ).data,
    onSuccess: onCreated,
  });

  const canCreate = legalName.trim().length > 0 && !create.isPending;

  return (
    <main className="min-h-screen bg-[#edf1f3] px-4 py-8 text-slate-800 sm:px-8 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8 flex items-start justify-between gap-6 border-b border-slate-300 pb-5">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-800">
              Superlight Invoice
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">
              Choose a company ledger
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">
              Invoices, payments and receipts — without the accounting software.
              No login is required.
            </p>
          </div>
          <div className="hidden border-l border-amber-600 pl-4 text-right sm:block">
            <div className="font-mono text-2xl font-semibold text-slate-900">
              {String(companies.length).padStart(2, "0")}
            </div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">
              company ledgers
            </div>
          </div>
        </header>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
          <section aria-label="Companies" className="space-y-3">
            {companies.map((company, index) => (
              <button
                key={company.id}
                className="group grid w-full grid-cols-[58px_minmax(0,1fr)_auto] items-center overflow-hidden rounded-lg border border-slate-300 bg-white text-left shadow-[0_1px_0_rgba(15,23,42,0.04)] transition hover:-translate-y-0.5 hover:border-emerald-700 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:ring-offset-2"
                onClick={() => onSelect(company)}
              >
                <span className="flex h-full min-h-[92px] flex-col items-center justify-center border-r border-slate-200 bg-slate-900 text-white">
                  <span className="text-lg font-semibold">{monogram(company) || "CO"}</span>
                  <span className="mt-1 font-mono text-[9px] tracking-widest text-slate-400">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                </span>
                <span className="min-w-0 px-4 py-4">
                  <span className="block truncate text-base font-semibold text-slate-900">
                    {displayName(company)}
                  </span>
                  {company.trading_name && (
                    <span className="mt-0.5 block truncate text-xs text-slate-500">
                      Legal name: {company.legal_name}
                    </span>
                  )}
                  <span className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
                    <span>{company.abn ? `ABN ${company.abn}` : "ABN not set"}</span>
                    <span>{company.gst_registered ? "GST registered" : "Not GST registered"}</span>
                  </span>
                </span>
                <span className="px-4 text-sm font-medium text-emerald-800 group-hover:text-emerald-950">
                  Open →
                </span>
              </button>
            ))}
          </section>

          <section className="self-start rounded-lg bg-slate-900 p-5 text-white shadow-lg">
            <div className="border-l-2 border-amber-500 pl-3">
              <h2 className="font-semibold">Add another company</h2>
              <p className="mt-1 text-xs leading-5 text-slate-400">
                Start a separate ledger. Company details and bank information can be completed
                after opening it.
              </p>
            </div>
            <label className="mt-5 block text-xs text-slate-300">
              Legal name *
              <input
                className="input mt-1 border-slate-600 bg-slate-800 text-white placeholder:text-slate-500"
                value={legalName}
                onChange={(event) => setLegalName(event.target.value)}
                placeholder="Registered company name"
              />
            </label>
            <label className="mt-3 block text-xs text-slate-300">
              Business name (optional)
              <input
                className="input mt-1 border-slate-600 bg-slate-800 text-white placeholder:text-slate-500"
                value={tradingName}
                onChange={(event) => setTradingName(event.target.value)}
                placeholder="Name shown to customers"
              />
            </label>
            {create.isError && (
              <p className="mt-3 rounded border border-rose-800 bg-rose-950/40 px-3 py-2 text-xs text-rose-200">
                {apiErrorMessage(create.error)}
              </p>
            )}
            <button
              className="mt-5 inline-flex h-[36px] w-full items-center justify-center rounded bg-emerald-600 px-3 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canCreate}
              onClick={() => create.mutate()}
            >
              {create.isPending ? "Creating…" : "Create and open"}
            </button>
          </section>
        </div>
      </div>
    </main>
  );
}
