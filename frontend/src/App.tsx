import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  addRestockItem,
  cancelDraft,
  confirmDraft,
  createManualEntry,
  fetchCustomerReminder,
  fetchCustomers,
  fetchDailySummary,
  fetchDraft,
  fetchLedger,
  fetchRestock,
  fetchSettings,
  processVoiceTranscript,
  saveSettings,
  selectCustomer,
  toggleRestockItem,
} from './api';
import {
  speakReadback,
  useSpeechRecognition,
} from './hooks/useSpeechRecognition';
import type {
  Customer,
  DailySummary,
  LedgerEntry,
  QueryResult,
  ReminderPreview,
  RestockItem,
  RoomStatus,
  WorkflowResponse,
} from './types';

const SESSION_STORAGE_KEY = 'udarvani_session_id';

function getOrCreateSessionId(): string {
  const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;
  const created = `shop-${Date.now().toString(36)}`;
  window.localStorage.setItem(SESSION_STORAGE_KEY, created);
  return created;
}

function formatInr(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '—';
  const num = Number(amount);
  const abs = Math.abs(num);
  const formatted = Number.isInteger(abs) ? abs.toString() : abs.toFixed(2);
  return num < 0 ? `-₹${formatted}` : `₹${formatted}`;
}

function formatQty(qty: number | null | undefined): string {
  if (qty === null || qty === undefined) return '—';
  return Number.isInteger(qty) ? qty.toString() : qty.toFixed(2);
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

export function App() {
  const [sessionId] = useState<string>(() => getOrCreateSessionId());
  const [lang, setLang] = useState<'hi-IN' | 'en-IN'>('hi-IN');
  const [voiceReadbackEnabled, setVoiceReadbackEnabled] = useState(true);

  const [workflow, setWorkflow] = useState<WorkflowResponse | null>(null);
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [ledgerEntries, setLedgerEntries] = useState<LedgerEntry[]>([]);
  const [historyMode, setHistoryMode] = useState<'all' | 'cash' | 'upi' | 'credit' | 'repayment'>('all');
  const [historySearch, setHistorySearch] = useState('');
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [dailySummary, setDailySummary] = useState<DailySummary | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerSearch, setCustomerSearch] = useState('');
  const [restockItems, setRestockItems] = useState<RestockItem[]>([]);
  const [newRestockText, setNewRestockText] = useState('');

  // Manual entry state
  const [showManualForm, setShowManualForm] = useState(false);
  const [manualMode, setManualMode] = useState<'cash' | 'upi' | 'credit' | 'repayment'>('cash');
  const [manualCustomerId, setManualCustomerId] = useState<string>('');
  const [manualAmount, setManualAmount] = useState('');
  const [manualPromisedDate, setManualPromisedDate] = useState('');
  const [manualReviewed, setManualReviewed] = useState(false);
  const manualInFlightRef = useRef(false);

  // Reminder & optional UPI settings
  const [reminderPreview, setReminderPreview] = useState<ReminderPreview | null>(null);
  const [merchantUpiId, setMerchantUpiId] = useState('');
  const [showSettings, setShowSettings] = useState(false);

  const [transcriptInput, setTranscriptInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState('');
  const [saveFailed, setSaveFailed] = useState(false);
  const [statusNotice, setStatusNotice] = useState('');

  const lastSpokenKeyRef = useRef<string>('');
  const confirmInFlightRef = useRef(false);
  const transcriptInFlightRef = useRef(false);

  const refreshAllData = useCallback(async () => {
    const [ledgerRes, custRes, summaryRes, restockRes] = await Promise.all([
      fetchLedger(),
      fetchCustomers(),
      fetchDailySummary(),
      fetchRestock(),
    ]);
    setLedgerEntries(ledgerRes.entries);
    setCustomers(custRes.customers);
    setDailySummary(summaryRes);
    setRestockItems(restockRes.items);
  }, []);

  const loadInitialData = useCallback(async () => {
    try {
      const [draftRes, settingsRes] = await Promise.all([
        fetchDraft(sessionId),
        fetchSettings(),
      ]);
      setWorkflow(draftRes);
      setMerchantUpiId(settingsRes.merchant_upi_id);
      await refreshAllData();
      setApiError('');
    } catch (err) {
      setApiError(
        err instanceof Error
          ? err.message
          : 'Could not reach UdarVani backend API.',
      );
    }
  }, [refreshAllData, sessionId]);

  useEffect(() => {
    void loadInitialData();
  }, [loadInitialData]);

  const speech = useSpeechRecognition({
    lang,
    onFinalTranscript: (spoken) => {
      void handleTranscriptSubmit(spoken);
    },
  });

  const speakOnce = useCallback(
    (text: string, dedupeKey: string, endVoiceAfter = false) => {
      if (!text.trim()) {
        if (endVoiceAfter) speech.endSession();
        return;
      }
      if (lastSpokenKeyRef.current === dedupeKey) return;
      lastSpokenKeyRef.current = dedupeKey;
      speakReadback(text, voiceReadbackEnabled, {
        onStart: speech.pauseForPlayback,
        onEnd: () => {
          if (endVoiceAfter) {
            speech.endSession();
          }
          speech.finishPlayback();
        },
      });
    },
    [speech, voiceReadbackEnabled],
  );

  const handleTranscriptSubmit = useCallback(
    async (text: string, balanceChoice = false) => {
      const cleaned = text.trim();
      if (!cleaned || transcriptInFlightRef.current || confirmInFlightRef.current) return;
      const isSimpleName = /^[\p{L}\p{M}][\p{L}\p{M} .'-]{0,60}$/u.test(cleaned)
        && cleaned.split(/\s+/).length <= 4;
      const request = balanceChoice || (queryResult?.kind === 'balance_ambiguous' && isSimpleName)
        ? `balance for ${cleaned}`
        : cleaned;
      transcriptInFlightRef.current = true;
      setBusy(true);
      setApiError('');
      setSaveFailed(false);
      setStatusNotice('');
      try {
        const res = await processVoiceTranscript(sessionId, request);
        if (res.end_voice_session) {
          speech.endSession();
        }
        if (res.query_result) {
          setQueryResult(res.query_result);
          if (res.readback_text) {
            lastSpokenKeyRef.current = '';
            speakOnce(
              res.readback_text,
              `query:${res.query_result.kind}:${res.readback_text}`,
              Boolean(res.end_voice_session),
            );
          }
          setTranscriptInput('');
          await refreshAllData();
          return;
        }
        setQueryResult(null);
        setWorkflow(res);
        setTranscriptInput('');
        await refreshAllData();
        if (res.readback_text) {
          const key = `${res.draft?.status ?? 'none'}:${res.draft?.clarification_field ?? ''}:${res.readback_text}`;
          if (lastSpokenKeyRef.current === key && !res.end_voice_session) {
            // Don't repeat the same prompt or leave an active turn with a dead mic.
            speech.finishPlayback();
          } else {
            speakOnce(res.readback_text, key, Boolean(res.end_voice_session));
          }
        }
        if (res.message) {
          setStatusNotice(res.message);
        }
      } catch (err) {
        setApiError(
          err instanceof Error ? err.message : 'Failed to process transcript.',
        );
      } finally {
        transcriptInFlightRef.current = false;
        setBusy(false);
      }
    },
    [queryResult?.kind, refreshAllData, sessionId, speakOnce, speech],
  );

  const handleSelectCustomer = async (customerId: number) => {
    setBusy(true);
    setApiError('');
    setSaveFailed(false);
    try {
      const res = await selectCustomer(sessionId, customerId);
      setWorkflow(res);
      if (res.readback_text) {
        const key = `${res.draft?.status ?? 'none'}:${customerId}:${res.readback_text}`;
        speakOnce(res.readback_text, key);
      }
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Failed to select customer.');
    } finally {
      setBusy(false);
    }
  };

  const handleConfirm = async () => {
    if (confirmInFlightRef.current || transcriptInFlightRef.current) return;
    confirmInFlightRef.current = true;
    setBusy(true);
    setApiError('');
    setSaveFailed(false);
    try {
      const res = await confirmDraft(sessionId);
      setWorkflow(res);
      await refreshAllData();
      if (res.end_voice_session) {
        speech.endSession();
      }
      if (res.readback_text) {
        speakOnce(
          res.readback_text,
          `saved:${res.last_saved_entry?.id ?? Date.now()}:${res.readback_text}`,
          Boolean(res.end_voice_session),
        );
      }
      setStatusNotice(res.message);
    } catch (err) {
      setSaveFailed(true);
      setApiError(
        err instanceof Error
          ? `Save failed: ${err.message}. Draft retained — tap Retry Save.`
          : 'Save failed. Draft retained — tap Retry Save.',
      );
    } finally {
      confirmInFlightRef.current = false;
      setBusy(false);
    }
  };

  const handleCancel = async () => {
    setBusy(true);
    setApiError('');
    setSaveFailed(false);
    setQueryResult(null);
    lastSpokenKeyRef.current = '';
    speech.endSession();
    try {
      const res = await cancelDraft(sessionId);
      setWorkflow(res);
      setStatusNotice(res.message || 'Draft cancelled. Nothing written.');
      if (res.readback_text) {
        speakOnce(res.readback_text, `cancel:${Date.now()}`, true);
      }
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Failed to cancel draft.');
    } finally {
      setBusy(false);
    }
  };

  const handleManualSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (manualInFlightRef.current || busy) return;
    const amt = Number(manualAmount);
    if (!amt || amt <= 0) return;
    if (!manualReviewed) {
      setManualReviewed(true);
      return;
    }
    manualInFlightRef.current = true;
    setBusy(true);
    setApiError('');
    try {
      await createManualEntry({
        payment_mode: manualMode,
        customer_id: manualCustomerId ? Number(manualCustomerId) : null,
        amount: amt,
        promised_date: manualPromisedDate || null,
      });
      setManualReviewed(false);
      setManualAmount('');
      setManualPromisedDate('');
      setStatusNotice(`Manual ${manualMode.toUpperCase()} ₹${amt} recorded.`);
      await refreshAllData();
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Manual save failed.');
    } finally {
      manualInFlightRef.current = false;
      setBusy(false);
    }
  };

  const handleOpenReminder = async (customerId: number) => {
    try {
      const rem = await fetchCustomerReminder(customerId);
      setReminderPreview(rem);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Could not load reminder.');
    }
  };

  const handleSaveSettings = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const saved = await saveSettings(merchantUpiId);
      setMerchantUpiId(saved.merchant_upi_id);
      setShowSettings(false);
      if (reminderPreview) await handleOpenReminder(reminderPreview.customer.id);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Could not save UPI settings.');
    }
  };

  const handleAddRestock = async (e: FormEvent) => {
    e.preventDefault();
    if (!newRestockText.trim()) return;
    try {
      await addRestockItem(newRestockText.trim());
      setNewRestockText('');
      setRestockItems((await fetchRestock()).items);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Could not add the restock item.');
    }
  };

  const handleToggleRestock = async (id: number) => {
    try {
      await toggleRestockItem(id);
      setRestockItems((await fetchRestock()).items);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Could not update the restock item.');
    }
  };

  const handleFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    void handleTranscriptSubmit(transcriptInput);
  };

  const roomStatus: RoomStatus = useMemo(() => {
    if (apiError || saveFailed) return 'Error';
    if (speech.isListening) return 'Listening';
    const st = workflow?.draft?.status;
    if (st === 'clarification_needed') return 'Needs clarification';
    if (st === 'awaiting_confirmation') return 'Ready to save';
    if (st === 'saved') return 'Saved';
    return 'Ready';
  }, [apiError, saveFailed, speech.isListening, workflow?.draft?.status]);

  const statusBadgeClass = useMemo(() => {
    switch (roomStatus) {
      case 'Listening':
        return 'status-pill status-listening';
      case 'Needs clarification':
        return 'status-pill status-clarify';
      case 'Ready to save':
        return 'status-pill status-confirm';
      case 'Saved':
        return 'status-pill status-saved';
      case 'Error':
        return 'status-pill status-error';
      default:
        return 'status-pill status-ready';
    }
  }, [roomStatus]);

  const filteredCustomers = useMemo(() => {
    const q = customerSearch.trim().toLowerCase();
    if (!q) return customers;
    return customers.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.label.toLowerCase().includes(q) ||
        c.phone_hint.toLowerCase().includes(q),
    );
  }, [customers, customerSearch]);

  const filteredHistory = ledgerEntries.filter((entry) => {
    const mode = entry.entry_type === 'repayment' ? 'repayment' : entry.payment_mode;
    const q = historySearch.trim().toLowerCase();
    return (historyMode === 'all' || historyMode === mode)
      && (!q || `${entry.customer_name} ${entry.item_name}`.toLowerCase().includes(q));
  });
  const visibleHistory = historyExpanded ? filteredHistory : filteredHistory.slice(0, 8);
  const draft = workflow?.draft ?? null;
  const candidates = workflow?.candidate_customers ?? [];
  const isDuplicateCustomerClarification =
    draft?.status === 'clarification_needed' &&
    draft.clarification_field === 'customer_choice' &&
    candidates.length > 1;
  const isYesNoClarification =
    draft?.status === 'clarification_needed' &&
    (draft.clarification_field === 'confirm_replace' ||
      draft.clarification_field === 'confirm_new_customer');
  const isDirectCredit = draft?.entry_type === 'direct_credit' || draft?.entry_type === 'repayment';
  const isReversal = draft?.entry_type === 'reversal';

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            उ
          </div>
          <div>
            <h1 className="brand-title">UdarVani</h1>
            <p className="brand-subtitle">Daily Kirana Ledger &amp; Credit Recovery</p>
          </div>
        </div>

        <div className="header-controls">
          <span
            className={statusBadgeClass}
            role="status"
            aria-live="polite"
            data-testid="room-status"
          >
            {roomStatus}
          </span>
          <button
            type="button"
            className="btn-secondary btn-compact"
            onClick={() => void handleTranscriptSubmit('evening summary')}
            data-testid="evening-summary-btn"
          >
            Evening Summary
          </button>
          <button
            type="button"
            className="btn-secondary btn-compact"
            onClick={() => setVoiceReadbackEnabled((v) => !v)}
            aria-pressed={voiceReadbackEnabled}
          >
            {voiceReadbackEnabled ? 'Voice: ON' : 'Voice: OFF'}
          </button>
          <button
            type="button"
            className="btn-secondary btn-compact"
            onClick={() => setShowSettings((s) => !s)}
          >
            UPI Setup
          </button>
        </div>
      </header>

      {showSettings && (
        <form className="card settings-bar" onSubmit={handleSaveSettings}>
          <label htmlFor="upi-input" className="transcript-label">
            Optional Merchant UPI ID (for payment reminder links only; no secrets required):
          </label>
          <div className="transcript-row">
            <input
              id="upi-input"
              type="text"
              className="text-input"
              value={merchantUpiId}
              onChange={(e) => setMerchantUpiId(e.target.value)}
              placeholder="e.g. myshop@upi"
            />
            <button type="submit" className="btn-primary">
              Save UPI
            </button>
          </div>
        </form>
      )}

      <main className="main-grid">
        {/* LEFT COLUMN (First on mobile): Mic + Prompt + Draft */}
        <section className="workspace-col" aria-label="Voice entry and draft">
          <div className="card mic-card">
            <div className="mic-header-row">
              <span className="section-eyebrow">1. Voice &amp; Manual Entry</span>
              <div className="lang-toggle" role="group" aria-label="Speech language">
                <button
                  type="button"
                  className={lang === 'hi-IN' ? 'lang-btn active' : 'lang-btn'}
                  onClick={() => setLang('hi-IN')}
                >
                  हिन्दी / Hinglish
                </button>
                <button
                  type="button"
                  className={lang === 'en-IN' ? 'lang-btn active' : 'lang-btn'}
                  onClick={() => setLang('en-IN')}
                >
                  English (IN)
                </button>
              </div>
            </div>

            <div className={`mic-ring ${speech.isListening ? 'is-listening' : ''}`}>
              <button
                type="button"
                className={`mic-button ${speech.isListening ? 'listening' : ''}`}
                onClick={
                  speech.isListening || speech.sessionActive
                    ? speech.stopListening
                    : speech.startListening
                }
                disabled={!speech.isSupported || busy || speech.isSpeaking}
                data-testid="mic-button"
              >
                <span className="mic-icon" aria-hidden="true">
                  {speech.isListening ? '■' : '🎙'}
                </span>
                <span className="mic-label">
                  {!speech.isSupported
                    ? 'Mic Unsupported in Browser'
                    : speech.isSpeaking
                      ? 'Speaking Readback…'
                      : speech.isListening
                        ? 'Listening… Tap to Stop'
                        : 'Tap & Speak'}
                </span>
              </button>
            </div>
            <p className="lang-roadmap">
              Active: Hindi/Hinglish &amp; English • Planned (unverified): Kannada, Tamil, Marathi
            </p>

            {speech.interimText && (
              <div className="interim-box" aria-live="polite">
                Hearing live: <strong>{speech.interimText}</strong>
              </div>
            )}

            {speech.errorKind && speech.errorMessage && (
              <div className="alert-box alert-error" role="alert" data-testid="mic-error">
                <div>
                  <strong>Microphone Notice:</strong> {speech.errorMessage}
                </div>
                {speech.isSupported && (
                  <button
                    type="button"
                    className="btn-secondary btn-compact"
                    onClick={speech.clearError}
                  >
                    Dismiss
                  </button>
                )}
              </div>
            )}

            {apiError && (
              <div className="alert-box alert-error" role="alert" data-testid="api-error">
                <span>{apiError}</span>
                {saveFailed && (
                  <button
                    type="button"
                    className="btn-primary btn-compact"
                    onClick={() => void handleConfirm()}
                    disabled={busy}
                    data-testid="retry-save-btn"
                  >
                    Retry Save
                  </button>
                )}
              </div>
            )}

            {/* Transcript Fallback Input */}
            <form
              className={`transcript-form ${speech.suggestManualFallback ? 'fallback-highlight' : ''}`}
              onSubmit={handleFormSubmit}
            >
              <label htmlFor="transcript-input" className="transcript-label">
                Typed Fallback (testing, accessibility &amp; noisy-shop recovery)
              </label>
              <div className="transcript-row">
                <input
                  id="transcript-input"
                  data-testid="transcript-input"
                  type="text"
                  className="text-input"
                  value={transcriptInput}
                  onChange={(e) => setTranscriptInput(e.target.value)}
                  placeholder="जैसे: राजीव ने तीस रुपये उधार लिए"
                  disabled={busy}
                />
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={busy || !transcriptInput.trim()}
                  data-testid="submit-transcript"
                >
                  {busy ? '…' : 'Send'}
                </button>
              </div>
              <div className="sample-chips">
                <button
                  type="button"
                  className="chip-btn"
                  onClick={() => setShowManualForm((v) => !v)}
                  data-testid="toggle-manual-btn"
                >
                  {showManualForm ? 'Hide Manual Form' : '+ Manual Cash / UPI / Credit'}
                </button>
                <button
                  type="button"
                  className="chip-btn"
                  onClick={() => setTranscriptInput('राजीव ने तीस रुपये उधार लिए')}
                >
                  राजीव ₹30
                </button>
                <button
                  type="button"
                  className="chip-btn"
                  onClick={() =>
                    setTranscriptInput('Ramesh Kumar ne do sau pachaas ka samaan liya, Friday ko denge')
                  }
                >
                  ₹250 Friday
                </button>
                <button
                  type="button"
                  className="chip-btn"
                  onClick={() => setTranscriptInput('Ramesh ne sau rupaye diye')}
                >
                  Repay ₹100
                </button>
              </div>
            </form>

            {showManualForm && (
              <form className="manual-form" onChange={() => setManualReviewed(false)} onSubmit={handleManualSubmit} data-testid="manual-form">
                <div className="manual-grid">
                  <select
                    className="text-input"
                    value={manualMode}
                    onChange={(e) =>
                      setManualMode(e.target.value as 'cash' | 'upi' | 'credit' | 'repayment')
                    }
                    aria-label="Payment mode"
                  >
                    <option value="cash">Cash Sale</option>
                    <option value="upi">UPI Sale</option>
                    <option value="credit">Credit (Udhaar)</option>
                    <option value="repayment">Repayment (Jama)</option>
                  </select>
                  <input
                    type="number"
                    step="0.01"
                    min="1"
                    className="text-input"
                    placeholder="Amount ₹"
                    aria-label="Manual amount in rupees"
                    value={manualAmount}
                    onChange={(e) => setManualAmount(e.target.value)}
                    required
                  />
                </div>
                {(manualMode === 'credit' || manualMode === 'repayment') && (
                  <div className="manual-grid">
                    <select
                      className="text-input"
                      value={manualCustomerId}
                      onChange={(e) => setManualCustomerId(e.target.value)}
                      required
                      aria-label="Select customer"
                    >
                      <option value="">Select customer…</option>
                      {customers.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name} ({c.label})
                        </option>
                      ))}
                    </select>
                    {manualMode === 'credit' && (
                      <input
                        type="date"
                        className="text-input"
                        value={manualPromisedDate}
                        onChange={(e) => setManualPromisedDate(e.target.value)}
                        aria-label="Promised payment date"
                      />
                    )}
                  </div>
                )}
                {manualReviewed && (
                  <p className="manual-review" role="status">
                    Review: {manualMode.toUpperCase()} · {formatInr(Number(manualAmount))}
                    {(manualMode === 'credit' || manualMode === 'repayment') &&
                      ` · ${customers.find((c) => c.id === Number(manualCustomerId))?.name ?? 'Unknown customer'}`}
                    {manualMode === 'credit' && manualPromisedDate && ` · Due ${manualPromisedDate}`}
                  </p>
                )}
                <button type="submit" className="btn-primary" disabled={busy}>
                  {manualReviewed ? 'Confirm & Record' : 'Review Manual Entry'}
                </button>
                {manualReviewed && (
                  <button type="button" className="btn-secondary" onClick={() => setManualReviewed(false)}>
                    Back to edit
                  </button>
                )}
              </form>
            )}
          </div>

          {/* Read-Only Voice Query Result Card */}
          {queryResult && (
            <div className="card query-card" data-testid="query-result-card">
              <div className="draft-header">
                <span className="section-eyebrow">Read-Only Query</span>
                <button
                  type="button"
                  className="btn-secondary btn-compact"
                  onClick={() => setQueryResult(null)}
                >
                  Close
                </button>
              </div>
              <h2 className="card-title">{queryResult.title}</h2>
              {queryResult.total !== undefined && (
                <div className="query-total tabular-nums" data-testid="query-total">
                  {formatInr(queryResult.total)}
                </div>
              )}
              {queryResult.kind === 'today_total' && (
                <div className="mode-pills">
                  <span>Cash: {formatInr(queryResult.cash_total)}</span>
                  <span>UPI: {formatInr(queryResult.upi_total)}</span>
                  <span>Credit: {formatInr(queryResult.credit_total)}</span>
                  <span>Repaid: {formatInr(queryResult.repayments_total)}</span>
                </div>
              )}
              {queryResult.advisor_note && (
                <p className="advisor-note">{queryResult.advisor_note}</p>
              )}
              <p className="query-note">{queryResult.note}</p>
              {queryResult.kind === 'balance_ambiguous' && queryResult.candidates?.map((customer) => (
                <button type="button" key={customer.id} className="balance-choice"
                  onClick={() => void handleTranscriptSubmit(customer.name, true)} disabled={busy}>
                  {customer.name} · {customer.label}
                </button>
              ))}

              {queryResult.overdue_customers && queryResult.overdue_customers.length > 0 && (
                <div className="overdue-box">
                  <strong>Overdue Promises:</strong>
                  <ul className="ledger-list compact-list">
                    {queryResult.overdue_customers.map((o) => (
                      <li key={o.customer.id} className="ledger-item">
                        <div>
                          <strong>{o.customer.name}</strong>
                          <span className="ledger-meta">Due {o.promised_date}</span>
                        </div>
                        <div className="overdue-actions">
                          <span className="ledger-amount tabular-nums">{formatInr(o.balance)}</span>
                          <button
                            type="button"
                            className="btn-secondary btn-compact"
                            onClick={() => void handleOpenReminder(o.customer.id)}
                          >
                            Remind
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {queryResult.customer && (queryResult.total ?? 0) > 0 && (
                <button
                  type="button"
                  className="btn-secondary btn-compact"
                  onClick={() => void handleOpenReminder(queryResult.customer!.id)}
                >
                  Draft Polite Reminder
                </button>
              )}
            </div>
          )}

          {/* Reminder Preview Panel */}
          {reminderPreview && (
            <div className="card reminder-card" data-testid="reminder-card">
              <div className="draft-header">
                <span className="section-eyebrow">Reminder Preview (No Auto-Send)</span>
                <button
                  type="button"
                  className="btn-secondary btn-compact"
                  onClick={() => setReminderPreview(null)}
                >
                  Close
                </button>
              </div>
              <p className="reminder-msg">
                <strong>To:</strong> {reminderPreview.customer.name} ({reminderPreview.customer.phone_hint})
              </p>
              <p className="reminder-body">{reminderPreview.message_preview}</p>
              <div className="action-row wrap-row">
                <a
                  href={reminderPreview.whatsapp_url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-secondary btn-compact"
                >
                  Share WhatsApp
                </a>
                <a href={reminderPreview.sms_url} className="btn-secondary btn-compact">
                  Open SMS
                </a>
                <button
                  type="button"
                  className="btn-secondary btn-compact"
                  onClick={() =>
                    speakReadback(reminderPreview.simulated_call_script, true, {
                      onStart: speech.pauseForPlayback,
                      onEnd: speech.finishPlayback,
                    })
                  }
                >
                  🔊 Simulated Reminder Call Playback
                </button>
              </div>
            </div>
          )}

          {/* Live Draft, Current Question & Confirmation Card */}
          <div className={`card draft-card ${draft ? 'draft-active' : ''}`} aria-label="Transaction draft">
            <div className="draft-header">
              <span className="section-eyebrow">
                2.{' '}
                {draft?.entry_type === 'repayment'
                  ? 'Repayment Draft'
                  : draft?.payment_mode === 'cash'
                    ? 'Cash Sale Draft'
                    : draft?.payment_mode === 'upi'
                      ? 'UPI Sale Draft'
                      : isDirectCredit
                        ? 'Direct Credit Draft'
                        : isReversal
                          ? 'Reversal Confirmation'
                          : 'Transaction Draft'}
              </span>
              {workflow?.readback_text && (
                <button
                  type="button"
                  className="btn-secondary btn-compact"
                  onClick={() =>
                    speakReadback(workflow.readback_text, true, {
                      onStart: speech.pauseForPlayback,
                      onEnd: speech.finishPlayback,
                    })
                  }
                >
                  🔊 Read Aloud
                </button>
              )}
            </div>

            {!draft && (
              <div className="empty-draft">
                <p className="empty-title">Ready for next entry</p>
                <p className="empty-desc">
                  Tap the mic once and speak naturally. Unconfirmed drafts never write to the ledger.
                </p>
                {statusNotice && (
                  <p className="notice-inline" role="status">
                    {statusNotice}
                  </p>
                )}
              </div>
            )}

            {draft && (
              <div className="draft-body">
                {draft.status === 'clarification_needed' && (
                  <div className="clarify-panel" role="region" data-testid="clarification-panel">
                    <p className="clarify-prompt">{draft.clarification_prompt}</p>

                    {isDuplicateCustomerClarification && (
                      <div className="candidate-grid">
                        {candidates.map((cust, index) => (
                          <button
                            key={cust.id}
                            type="button"
                            className="candidate-card"
                            onClick={() => void handleSelectCustomer(cust.id)}
                            disabled={busy}
                            data-testid={`select-customer-${cust.id}`}
                          >
                            <span className="cand-index">Option {index + 1}</span>
                            <strong className="cand-name">{cust.name}</strong>
                            <span className="cand-label">{cust.label}</span>
                            <span className="cand-phone">{cust.phone_hint}</span>
                          </button>
                        ))}
                      </div>
                    )}

                    {isYesNoClarification && (
                      <div className="action-row">
                        <button
                          type="button"
                          className="btn-confirm"
                          onClick={() => void handleTranscriptSubmit('हाँ')}
                          disabled={busy}
                          data-testid="yes-clarify-btn"
                        >
                          ✓ Yes (हाँ)
                        </button>
                        <button
                          type="button"
                          className="btn-cancel"
                          onClick={() => void handleTranscriptSubmit('नहीं')}
                          disabled={busy}
                          data-testid="no-clarify-btn"
                        >
                          ✕ No (नहीं)
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Primary Resolved Customer & Amount */}
                <div className="draft-summary-grid">
                  {(draft.payment_mode === 'credit' || draft.entry_type === 'repayment' || draft.customer_id) && (
                    <div className="summary-cell">
                      <span className="cell-label">Customer</span>
                      <span className="cell-value" data-testid="draft-customer">
                        {workflow?.selected_customer
                          ? `${workflow.selected_customer.name} (${workflow.selected_customer.label})`
                          : draft.pending_new_customer
                            ? `${draft.pending_new_customer} (New?)`
                            : draft.customer_query
                              ? `${draft.customer_query} (Clarify)`
                              : '—'}
                      </span>
                    </div>
                  )}

                  <div className="summary-cell total-cell">
                    <span className="cell-label">
                      {isReversal ? 'Reversal' : draft.entry_type === 'repayment' ? 'Repaid Amount' : 'Amount'}
                    </span>
                    <span className="cell-total tabular-nums" data-testid="draft-total">
                      {formatInr(draft.total_amount)}
                    </span>
                  </div>

                  {!isDirectCredit && !isReversal && (
                    <>
                      <div className="summary-cell">
                        <span className="cell-label">Item</span>
                        <span className="cell-value" data-testid="draft-item">
                          {draft.item_name ?? '—'}
                        </span>
                      </div>
                      <div className="summary-cell">
                        <span className="cell-label">Calculation</span>
                        <span className="cell-value tabular-nums" data-testid="draft-calc">
                          {formatQty(draft.quantity)} × {formatInr(draft.unit_price)}
                        </span>
                      </div>
                    </>
                  )}

                  {draft.promised_date && (
                    <div className="summary-cell">
                      <span className="cell-label">Promised Date</span>
                      <span className="cell-value" data-testid="draft-promised-date">
                        {draft.promised_date}
                      </span>
                    </div>
                  )}
                </div>

                {draft.changed_fields.length > 0 && (
                  <div className="changes-row" data-testid="changed-fields">
                    {draft.changed_fields.map((chg, idx) => (
                      <span key={idx} className="change-badge">
                        Corrected {chg.field}: {String(chg.from ?? '—')} → {String(chg.to ?? '—')}
                      </span>
                    ))}
                  </div>
                )}

                {draft.status === 'awaiting_confirmation' && (
                  <div className="readback-banner" data-testid="readback-banner">
                    <strong>Readback:</strong> {workflow?.readback_text}
                  </div>
                )}

                {draft.status === 'saved' && workflow?.last_saved_entry && (
                  <div className="saved-receipt" data-testid="saved-banner">
                    <div className="receipt-header">
                      <span className="receipt-badge">✓ Saved Receipt</span>
                      <span className="receipt-amount tabular-nums">
                        {formatInr(workflow.last_saved_entry.total_amount)}
                      </span>
                    </div>
                    <div className="receipt-detail">
                      {workflow.last_saved_entry.customer_name} •{' '}
                      {workflow.last_saved_entry.item_name || 'Credit'}
                      {workflow.last_saved_entry.promised_date
                        ? ` • Due ${workflow.last_saved_entry.promised_date}`
                        : ''}
                    </div>
                  </div>
                )}

                <div className="heard-secondary">
                  <span className="meta-label">Heard:</span>
                  <span className="heard-quote" data-testid="heard-text">
                    “{draft.heard_text}”
                  </span>
                </div>

                <div className="action-row">
                  {draft.status !== 'saved' ? (
                    <>
                      <button
                        type="button"
                        className="btn-confirm"
                        onClick={() => void handleConfirm()}
                        disabled={busy || draft.status !== 'awaiting_confirmation'}
                        data-testid="confirm-btn"
                      >
                        ✓ Confirm &amp; Save
                      </button>
                      <button
                        type="button"
                        className="btn-cancel"
                        onClick={() => void handleCancel()}
                        disabled={busy}
                        data-testid="cancel-btn"
                      >
                        ✕ Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => {
                        lastSpokenKeyRef.current = '';
                        setWorkflow((prev) => (prev ? { ...prev, draft: null } : null));
                      }}
                      data-testid="new-entry-btn"
                    >
                      + Start New Entry
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* RIGHT COLUMN: Daily Totals + Confirmed Ledger + Restock & Customers */}
        <section className="ledger-col" aria-label="Daily totals and ledger">
          {dailySummary && (
            <div className="card summary-strip" data-testid="daily-summary-strip">
              <div className="summary-strip-top">
                <span className="section-eyebrow">Today’s Sales (Excl. Repayments)</span>
                <strong className="credit-total tabular-nums" data-testid="today-sales-total">
                  {formatInr(dailySummary.sales_total)}
                </strong>
              </div>
              <div className="mode-pills">
                <span>Cash: {formatInr(dailySummary.cash_total)}</span>
                <span>UPI: {formatInr(dailySummary.upi_total)}</span>
                <span>Credit: {formatInr(dailySummary.credit_total)}</span>
                <span>Repaid: {formatInr(dailySummary.repayments_total)}</span>
              </div>
            </div>
          )}

          <div className="card ledger-card">
            <div className="ledger-header">
              <div>
                <span className="section-eyebrow">3. Confirmed Ledger</span>
                <h2 className="card-title">Transaction history</h2>
              </div>
            </div>

            <div className="history-controls" role="group" aria-label="Filter transaction history">
              <input className="text-input" type="search" placeholder="Find customer or item"
                aria-label="Search transaction history" value={historySearch}
                onChange={(e) => { setHistorySearch(e.target.value); setHistoryExpanded(false); }} />
              <select className="text-input" aria-label="Filter history by payment type" value={historyMode}
                onChange={(e) => { setHistoryMode(e.target.value as typeof historyMode); setHistoryExpanded(false); }}>
                <option value="all">All transactions</option>
                <option value="cash">Cash</option>
                <option value="upi">UPI</option>
                <option value="credit">Credit</option>
                <option value="repayment">Repayment</option>
              </select>
            </div>
            {filteredHistory.length === 0 ? (
              <p className="empty-desc">
                {ledgerEntries.length ? 'No transactions match these filters.' : 'No confirmed entries yet. Speak or add a manual entry to get started.'}
              </p>
            ) : (
              <ul className="ledger-list" data-testid="ledger-list">
                {visibleHistory.map((entry) => (
                  <li
                    key={entry.id}
                    className={`ledger-item ${entry.entry_type === 'reversal' ? 'ledger-reversal' : entry.entry_type === 'repayment' ? 'ledger-repayment' : ''}`}
                  >
                    <div className="ledger-item-main">
                      <div className="ledger-cust-row">
                        <strong className="ledger-cust">{entry.customer_name}</strong>
                        <span className="ledger-label-tag">
                          {entry.entry_type === 'repayment'
                            ? 'REPAID'
                            : entry.payment_mode.toUpperCase()}
                        </span>
                        {entry.promised_date && (
                          <span className="ledger-label-tag">Due {entry.promised_date}</span>
                        )}
                        {entry.reversed_by_id && <span className="reversed-tag">Reversed</span>}
                      </div>
                      <div className="ledger-meta">
                        <span>
                          {entry.entry_type === 'itemized_sale'
                            ? `${formatQty(entry.quantity)} × ${entry.item_name} @ ${formatInr(entry.unit_price)}`
                            : entry.item_name}
                        </span>
                        <span className="ledger-time">{formatTime(entry.created_at)}</span>
                      </div>
                    </div>
                    <div className="ledger-amount tabular-nums">
                      {formatInr(entry.total_amount)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {filteredHistory.length > 8 && (
              <button type="button" className="btn-secondary history-more" aria-expanded={historyExpanded}
                onClick={() => setHistoryExpanded((value) => !value)}>
                {historyExpanded ? 'Show recent 8' : `Show all ${filteredHistory.length} matches`}
              </button>
            )}
          </div>

          <div className="card customers-card">
            <div className="customers-header">
              <div>
                <span className="section-eyebrow">Customer Accounts</span>
                <h2 className="card-title">Khata Directory</h2>
              </div>
              <input
                type="search"
                className="search-input"
                placeholder="Search customer…"
                value={customerSearch}
                onChange={(e) => setCustomerSearch(e.target.value)}
                aria-label="Search customer accounts"
              />
            </div>

            <ul className="customer-list">
              {filteredCustomers.map((c) => (
                <li key={c.id} className="customer-row">
                  <div>
                    <strong>{c.name}</strong>
                    <span className="cust-sub">{c.label}</span>
                  </div>
                  <button
                    type="button"
                    className="btn-secondary btn-compact"
                    onClick={() => void handleOpenReminder(c.id)}
                  >
                    Remind / Bal
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="card restock-card">
            <span className="section-eyebrow">Restock List (Voice or Tap)</span>
            <form className="transcript-row" onSubmit={handleAddRestock}>
              <input
                type="text"
                className="text-input"
                placeholder="Add item to restock…"
                value={newRestockText}
                onChange={(e) => setNewRestockText(e.target.value)}
              />
              <button type="submit" className="btn-secondary">
                Add
              </button>
            </form>
            {restockItems.length > 0 && (
              <ul className="customer-list compact-list">
                {restockItems.map((it) => (
                  <li key={it.id} className="customer-row">
                    <label className={it.done ? 'restock-done' : ''}>
                      <input
                        type="checkbox"
                        checked={Boolean(it.done)}
                        onChange={() => void handleToggleRestock(it.id)}
                      />{' '}
                      {it.item_name}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
