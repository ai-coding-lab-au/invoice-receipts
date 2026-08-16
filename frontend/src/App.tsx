import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import CompanyChooser from "./components/CompanyChooser";
import { api, getActiveCompanyId, setActiveCompanyId } from "./lib/api";
import type { Company } from "./types/api";
import InvoicesPage from "./pages/Invoices";
import ClientsPage from "./pages/Clients";
import SettingsPage from "./pages/Settings";

const NAV = [
  { to: "/invoices", label: "Invoices" },
  { to: "/clients", label: "Clients" },
  { to: "/settings", label: "Settings" },
];

export default function App() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [activeCompanyId, setActiveId] = useState<number | null>(() => getActiveCompanyId());
  const companies = useQuery({
    queryKey: ["companies"],
    queryFn: async () => (await api.get<Company[]>("/companies")).data,
  });

  useEffect(() => {
    if (!companies.data || activeCompanyId === null) return;
    if (!companies.data.some((company) => company.id === activeCompanyId)) {
      setActiveCompanyId(null);
      setActiveId(null);
    }
  }, [activeCompanyId, companies.data]);

  const clearCompanyQueries = async () => {
    await queryClient.cancelQueries({
      predicate: (query) => query.queryKey[0] !== "companies",
    });
    queryClient.removeQueries({
      predicate: (query) => query.queryKey[0] !== "companies",
    });
  };

  const selectCompany = async (company: Company) => {
    await clearCompanyQueries();
    setActiveCompanyId(company.id);
    setActiveId(company.id);
    navigate("/invoices", { replace: true });
  };

  if (companies.isLoading) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">Loading companies…</div>;
  }
  if (companies.isError || !companies.data) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-rose-700">Unable to load companies.</div>;
  }

  const activeCompany = companies.data.find((company) => company.id === activeCompanyId);
  if (!activeCompany) {
    return (
      <CompanyChooser
        companies={companies.data}
        onSelect={selectCompany}
        onCreated={(company) => {
          queryClient.setQueryData<Company[]>(["companies"], (current = []) => [
            ...current,
            company,
          ]);
          selectCompany(company);
        }}
      />
    );
  }

  return (
    <Workspace
      key={activeCompany.id}
      companyId={activeCompany.id}
      onSwitchCompany={async () => {
        await clearCompanyQueries();
        setActiveCompanyId(null);
        setActiveId(null);
      }}
    />
  );
}

function Workspace({
  companyId,
  onSwitchCompany,
}: {
  companyId: number;
  onSwitchCompany: () => void;
}) {
  const company = useQuery({
    queryKey: ["company", companyId],
    queryFn: async () => (await api.get<Company>("/company")).data,
  });

  return (
    <div className="flex min-h-screen flex-col">
      <header className="bg-slate-900 text-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">
              {company.data?.trading_name || company.data?.legal_name || "Invoice & Receipts"}
            </div>
            <div className="text-xs text-slate-400">
              {company.data?.gst_registered ? "GST registered" : "Not GST registered"}
              {company.data?.abn ? ` · ABN ${company.data.abn}` : ""}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <nav className="flex gap-1">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `rounded px-3 py-1.5 text-sm ${
                      isActive ? "bg-white text-slate-900" : "text-slate-300 hover:bg-slate-800"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
            <button
              className="rounded border border-slate-600 px-2.5 py-1.5 text-xs text-slate-300 hover:border-slate-400 hover:text-white"
              onClick={onSwitchCompany}
            >
              Switch company
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Routes>
          <Route path="/" element={<Navigate to="/invoices" replace />} />
          <Route path="/invoices" element={<InvoicesPage />} />
          <Route path="/clients" element={<ClientsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/invoices" replace />} />
        </Routes>
      </main>
    </div>
  );
}
