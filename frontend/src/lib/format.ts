export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const match = value.slice(0, 10).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value;
}

/**
 * Local DD/MM/YYYY HH:mm. The API sends an explicit UTC offset, so `new Date`
 * converts to the operator's timezone rather than treating UTC as local.
 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return `$${n.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function statusLabel(status: string): string {
  if (status === "partially_paid") return "Partially paid";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function statusBadgeClass(status: string): string {
  switch (status) {
    case "paid":
      return "bg-emerald-100 text-emerald-800";
    case "partially_paid":
      return "bg-amber-100 text-amber-800";
    case "void":
      return "bg-rose-100 text-rose-800";
    default:
      return "bg-slate-200 text-slate-700";
  }
}

export function pluralise(count: number, singular: string, plural?: string): string {
  return `${count} ${count === 1 ? singular : plural ?? singular + "s"}`;
}

/** Strip thousands separators so a pasted "1,000.00" parses cleanly. */
export function stripMoney(value: string): string {
  return (value ?? "").replace(/,/g, "").trim();
}

/** null when the value is a clean 2-decimal amount, otherwise why it is not. */
export function moneyProblem(value: string): string | null {
  const trimmed = stripMoney(value);
  if (!trimmed) return "is required";
  if (!/^\d+(?:\.\d{1,2})?$/.test(trimmed)) return "is not a valid dollar amount";
  if (Number(trimmed) > 999999999999.99) return "is above the supported maximum";
  return null;
}
