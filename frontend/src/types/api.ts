export interface Company {
  id: number;
  legal_name: string;
  trading_name: string | null;
  abn: string | null;
  gst_registered: boolean;
  address_line1: string | null;
  address_line2: string | null;
  suburb: string | null;
  state: string | null;
  postcode: string | null;
  phone: string | null;
  email: string | null;
  bank_account_name: string | null;
  bank_name: string | null;
  bank_bsb: string | null;
  bank_account_number: string | null;
  bank_swift: string | null;
  payment_terms_days: number;
  updated_at: string;
}

export interface Client {
  id: number;
  company_id: number;
  display_name: string;
  abn: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
}

export interface DocumentLine {
  id: number;
  order_no: number;
  description: string;
  quantity: string;
  unit_price: string;
  amount: string;
  gst_treatment: "taxable" | "gst_free";
}

export interface ReceiptSummary {
  id: number;
  doc_number: string;
  status: string;
  total: string;
  paid_date: string | null;
  payment_method: string | null;
}

export interface DocumentRecord {
  id: number;
  company_id: number;
  doc_type: "invoice" | "receipt";
  doc_number: string;
  issue_date: string;
  due_date: string | null;
  client_id: number | null;
  invoice_id: number | null;
  customer_name: string;
  customer_abn: string | null;
  customer_address: string | null;
  customer_email: string | null;
  customer_phone: string | null;
  currency: string;
  subtotal: string;
  gst_amount: string;
  total: string;
  gst_inclusive: boolean;
  status: string;
  paid_date: string | null;
  payment_method: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  lines: DocumentLine[];
  receipts: ReceiptSummary[];
  amount_received: string | null;
  amount_outstanding: string | null;
  can_edit: boolean;
  edit_block_reason: string | null;
}

export interface DocumentEvent {
  id: number;
  document_id: number;
  action: string;
  operator: string;
  reason: string;
  snapshot: Record<string, unknown> | null;
  occurred_at: string;
}

export interface AuditAction {
  operator: string;
  reason: string;
}

export interface InvoiceLineInput {
  description: string;
  quantity: string;
  unit_price: string;
  gst_treatment: "taxable" | "gst_free";
}
