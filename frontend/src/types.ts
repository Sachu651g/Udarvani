export interface Customer {
  id: number;
  name: string;
  label: string;
  phone_hint: string;
  aliases?: string[];
}

export interface ChangedField {
  field: string;
  from: string | number | null;
  to: string | number | null;
}

export type EntryType = 'itemized_sale' | 'direct_credit' | 'repayment' | 'reversal';
export type PaymentMode = 'credit' | 'cash' | 'upi';

export type DraftStatus =
  | 'clarification_needed'
  | 'awaiting_confirmation'
  | 'saved'
  | 'cancelled';

export type RoomStatus =
  | 'Ready'
  | 'Listening'
  | 'Needs clarification'
  | 'Ready to save'
  | 'Saved'
  | 'Error';

export interface DraftSession {
  session_id: string;
  status: DraftStatus;
  entry_type: EntryType;
  payment_mode: PaymentMode;
  clarification_field: string;
  customer_id: number | null;
  customer_query: string | null;
  candidate_customer_ids: number[];
  pending_new_customer: string | null;
  item_name: string | null;
  quantity: number | null;
  unit_label: string;
  unit_price: number | null;
  total_amount: number | null;
  promised_date: string | null;
  reversal_target_id: number | null;
  heard_text: string;
  interpretation: string;
  changed_fields: ChangedField[];
  clarification_prompt: string;
  updated_at: string;
}

export interface LedgerEntry {
  id: number;
  session_id: string | null;
  entry_type: EntryType;
  payment_mode: PaymentMode;
  customer_id: number | null;
  customer_name: string;
  customer_label: string;
  item_name: string;
  quantity: number | null;
  unit_label: string;
  unit_price: number | null;
  total_amount: number;
  promised_date: string | null;
  reverses_entry_id: number | null;
  reversed_by_id: number | null;
  raw_transcript: string;
  created_at: string;
}

export interface OverdueCustomer {
  customer: Customer;
  balance: number;
  promised_date: string;
}

export interface DailySummary {
  date: string;
  count: number;
  sales_total: number;
  cash_total: number;
  upi_total: number;
  credit_total: number;
  repayments_total: number;
  overdue_customers: OverdueCustomer[];
}

export interface QueryResult {
  kind: 'today_total' | 'customer_balance' | 'balance_ambiguous';
  title: string;
  total?: number;
  cash_total?: number;
  upi_total?: number;
  credit_total?: number;
  repayments_total?: number;
  overdue_customers?: OverdueCustomer[];
  count?: number;
  entries?: LedgerEntry[];
  candidates?: Customer[];
  customer?: Customer;
  advisor_note?: string;
  note: string;
}

export interface WorkflowResponse {
  draft: DraftSession | null;
  selected_customer: Customer | null;
  candidate_customers: Customer[];
  last_saved_entry: LedgerEntry | null;
  readback_text: string;
  message: string;
  query_result?: QueryResult | null;
  end_voice_session?: boolean;
}

export interface LedgerResponse {
  entries: LedgerEntry[];
  count: number;
  total_credit: number;
  daily_summary?: DailySummary;
}

export interface ReminderPreview {
  customer: Customer;
  balance: number;
  upi_configured: boolean;
  upi_link: string;
  message_preview: string;
  whatsapp_url: string;
  sms_url: string;
  simulated_call_script: string;
}

export interface RestockItem {
  id: number;
  item_name: string;
  done: number;
  created_at: string;
}
