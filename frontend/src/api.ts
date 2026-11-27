import type {
  Customer,
  DailySummary,
  LedgerEntry,
  LedgerResponse,
  ReminderPreview,
  RestockItem,
  WorkflowResponse,
} from './types';

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const errBody = await res.text();
    throw new Error(errBody || `Request failed with status ${res.status}`);
  }
  return (await res.json()) as T;
}

export function fetchCustomers(query?: string): Promise<{ customers: Customer[] }> {
  const qs = query?.trim() ? `?q=${encodeURIComponent(query.trim())}` : '';
  return requestJson<{ customers: Customer[] }>(`/api/customers${qs}`);
}

export function fetchLedger(): Promise<LedgerResponse> {
  return requestJson<LedgerResponse>('/api/ledger');
}

export function fetchDailySummary(): Promise<DailySummary> {
  return requestJson<DailySummary>('/api/summary/daily');
}

export function fetchDraft(sessionId: string): Promise<WorkflowResponse> {
  return requestJson<WorkflowResponse>(
    `/api/draft?session_id=${encodeURIComponent(sessionId)}`,
  );
}

export function processVoiceTranscript(
  sessionId: string,
  transcript: string,
): Promise<WorkflowResponse> {
  return requestJson<WorkflowResponse>('/api/voice/process', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, transcript }),
  });
}

export function selectCustomer(
  sessionId: string,
  customerId: number,
): Promise<WorkflowResponse> {
  return requestJson<WorkflowResponse>('/api/draft/select-customer', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, customer_id: customerId }),
  });
}

export function confirmDraft(sessionId: string): Promise<WorkflowResponse> {
  return requestJson<WorkflowResponse>('/api/draft/confirm', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function cancelDraft(sessionId: string): Promise<WorkflowResponse> {
  return requestJson<WorkflowResponse>('/api/draft/cancel', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function createManualEntry(payload: {
  payment_mode: 'cash' | 'upi' | 'credit' | 'repayment';
  customer_id?: number | null;
  amount: number;
  promised_date?: string | null;
}): Promise<{ entry: LedgerEntry; message: string }> {
  return requestJson<{ entry: LedgerEntry; message: string }>('/api/ledger/manual', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchCustomerReminder(customerId: number): Promise<ReminderPreview> {
  return requestJson<ReminderPreview>(`/api/customers/${customerId}/reminder`);
}

export function fetchSettings(): Promise<{ merchant_upi_id: string }> {
  return requestJson<{ merchant_upi_id: string }>('/api/settings');
}

export function saveSettings(merchantUpiId: string): Promise<{ merchant_upi_id: string }> {
  return requestJson<{ merchant_upi_id: string }>('/api/settings', {
    method: 'POST',
    body: JSON.stringify({ merchant_upi_id: merchantUpiId }),
  });
}

export function fetchRestock(): Promise<{ items: RestockItem[] }> {
  return requestJson<{ items: RestockItem[] }>('/api/restock');
}

export function addRestockItem(itemName: string): Promise<{ item: RestockItem }> {
  return requestJson<{ item: RestockItem }>('/api/restock', {
    method: 'POST',
    body: JSON.stringify({ item_name: itemName }),
  });
}

export function toggleRestockItem(itemId: number): Promise<{ item: RestockItem }> {
  return requestJson<{ item: RestockItem }>(`/api/restock/${itemId}/toggle`, {
    method: 'POST',
  });
}
