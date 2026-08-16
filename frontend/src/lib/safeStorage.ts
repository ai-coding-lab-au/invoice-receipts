// localStorage access that can never break the workflow (SILENT-FE-002).
//
// Browsers throw from localStorage in private mode, under storage quota
// pressure, or when storage is disabled by policy. Operator-name persistence
// is a convenience only: a failed read falls back to the in-memory copy (or
// empty), and a failed write must never turn a successful API operation into
// a UI exception.

const memory = new Map<string, string>();

export const safeStorage = {
  getItem(key: string): string | null {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return memory.get(key) ?? null;
    }
  },
  setItem(key: string, value: string): void {
    memory.set(key, value);
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Keep the in-memory copy; persistence is best-effort.
    }
  },
  removeItem(key: string): void {
    memory.delete(key);
    try {
      window.localStorage.removeItem(key);
    } catch {
      // The in-memory value is already gone.
    }
  },
};
