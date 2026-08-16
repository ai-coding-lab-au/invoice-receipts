import axios from "axios";
import type { AxiosResponse } from "axios";

import { safeStorage } from "./safeStorage";

const ACTIVE_COMPANY_KEY = "invoice-receipts-active-company";

export interface LimitedList<T> {
  items: T[];
  total: number;
  truncated: boolean;
}

export function limitedList<T>(response: AxiosResponse<T[]>): LimitedList<T> {
  const header = Number(response.headers["x-total-count"]);
  const total = Number.isFinite(header) ? header : response.data.length;
  return {
    items: response.data,
    total,
    truncated:
      response.headers["x-result-truncated"] === "true" || total > response.data.length,
  };
}

export const api = axios.create({ baseURL: "/api/v1", timeout: 15000 });

export function getActiveCompanyId(): number | null {
  const value = Number(safeStorage.getItem(ACTIVE_COMPANY_KEY));
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

export function setActiveCompanyId(companyId: number | null): void {
  if (companyId === null) {
    safeStorage.removeItem(ACTIVE_COMPANY_KEY);
    delete api.defaults.headers.common["X-Company-ID"];
    return;
  }
  safeStorage.setItem(ACTIVE_COMPANY_KEY, String(companyId));
  api.defaults.headers.common["X-Company-ID"] = String(companyId);
}

setActiveCompanyId(getActiveCompanyId());
