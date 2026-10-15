import { createContext, ReactNode, useContext, useEffect, useState } from 'react';

import { C } from '@/constants/theme';
import offline from '@/data/demo-offline.json';

const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? '').replace(/\/+$/, '');

export type Reason = { type: 'green' | 'red' | 'info'; en: string; ar: string; egp: number | null };
export type Calc = {
  available: number;
  blocked: 'no_salary_seen' | 'unpaid_last_cycle' | 'salary_overdue' | null;
  expected_payday: string; // next payday expected from the median pay day
  overdue_days: number; // days past expected_payday with no salary (more than 5 → salary_overdue)
  needs_review: boolean;
  hr_salary: number;
  salary_deposits: number[];
  salary_used: number;
  last_payday: string;
  days_passed: number;
  days_in_cycle: number;
  earned: number;
  tier: string;
  tier_rate: number;
  rate_source: Mode;
  base_rate: number; // the tier rate (Rules) or the AI's rate
  booster_points: number;
  gig_income_30d: number;
  gig_weeks_30d: number;
  gig_apps: string[];
  wallet_adjustment: number;
  rate: number;
  cap: number;
  withdrawn: number;
  fee: number;
  overuse_warning: boolean;
};
export type Demo = {
  available: number;
  tier: string | null;
  reasons: Reason[];
  what_if: Reason | null;
  calc: Calc;
  booster_next: { points: number; egp: number; weeks: number } | null;
  to_review: number; // incoming payments still waiting for the "Identify this payment" survey
  mode: Mode;
  ai: Ai | null; // only in AI mode
  user: { key: DemoUser; title: string; persona: string; source_user?: string; source_today?: string; hr_salary: number };
  health: Health; // coaching only: never changes the amount (backend/health.py)
};
export const BAND_COLOR: Record<Health['band'], string> = {
  'Needs attention': C.red,
  Fair: C.amber,
  Good: '#A5B4FC',
  Excellent: C.green,
};
export type Health = {
  score: number;
  band: 'Needs attention' | 'Fair' | 'Good' | 'Excellent';
  window_end: string; // the 30 days end at the user's last SMS, not today
  spent_30d: number;
  categories: { key: string; label: string; egp: number }[]; // biggest first
  factors: { key: string; label: string; points: number; max: number; reason: string }[];
  tip: { text: string; gain: number };
};
export type Mode = 'rules' | 'ai';
export type DemoUser = 'main' | 'high' | 'medium' | 'low' | 'job_loss';
export type Ai = {
  p: number; // chance the next salary arrives on time and in full (0–1)
  rate: number;
  needs_review: boolean;
  paragraph: string | null;
  what_if_egp: number | null;
  notes: string[]; // fallbacks used for missing data
  contributions: { feature: string; label: string; value: number; score: number }[];
  start: number;
  score: number;
};
export type ReviewStatus =
  | 'needs_review'
  | 'user_reported'
  | 'awaiting_evidence'
  | 'verified'
  | 'flagged'
  | 'reversed';
export type Review = {
  tx_id: string;
  status: ReviewStatus;
  answer: string | null;
  details: string | null;
  evidence: 'now' | 'later' | 'none' | null;
  remembered: boolean; // answer copied from an earlier payment by the same person
  flag_reason: string | null;
  amount: number;
  counterparty: string | null;
};
export type SurveyAnswer = {
  tx_id: string;
  answer: string;
  details: string;
  evidence: 'now' | 'later' | 'none';
  image?: string; // base64
};
export type Sms = {
  id: number | string;
  sender: string;
  date: string;
  body: string;
  amount: number | null;
  direction: 'in' | 'out' | null;
  label: 'salary' | 'gig_income' | 'spending' | 'ignore';
  review: Review | null;
};
export type HistoryItem = {
  type: 'withdrawal' | 'repayment';
  date: string;
  amount: number;
  method?: string;
  on_time?: boolean;
};
export type History = {
  today: string;
  tier: string;
  items: HistoryItem[];
  on_time_streak: number;
  next_tier: string | null;
  next_tier_streak: number | null;
  next_tier_rate: number | null;
};
export type Method = 'bank' | 'wallet';
export type PastedSms = { id: string; body: string; sender: string; date: string };
export type Analysis = {
  sender: string;
  date: string;
  body: string;
  amount: number | null;
  direction: 'in' | 'out' | null;
  label: Sms['label'];
  why: string[];
  effect: { before: number; after: number; difference: number; changes: string[] };
  ml: { label: MlLabel | 'needs_review'; confidence: number; best_guess: MlLabel };
  review: Review | null;
};
export type MlLabel = Sms['label'] | 'transfer_in' | 'transfer_out';

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000); // a slow tunnel should not freeze the demo
  try {
    const res = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal });
    if (!res.ok) throw new Error(JSON.stringify((await res.json().catch(() => null))?.detail ?? `HTTP ${res.status}`));
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

type Store = {
  demo: Demo | null;
  inbox: Sms[] | null;
  history: History | null;
  offline: boolean;
  withTalabat: boolean;
  setWithTalabat: (on: boolean) => void;
  method: Method;
  setMethod: (m: Method) => void;
  mode: Mode;
  setMode: (m: Mode) => void;
  user: DemoUser;
  setUser: (u: DemoUser) => void; // also clears this session's withdrawals (they belonged to the previous user)
  withdrawals: HistoryItem[]; // made in the app this session; the backend subtracts them
  withdraw: (amount: number) => void;
  added: PastedSms[]; // SMS added in the Try SMS tab; the backend counts them like real ones
  addSms: (sms: PastedSms) => void;
  clearAdded: () => void;
  analyze: (sms: Omit<PastedSms, 'id'>) => Promise<Analysis>;
  submitSurvey: (answer: SurveyAnswer) => Promise<Review>;
  verifyPayment: (txId: string) => Promise<Review>; // demo admin action
};

const post = <T,>(path: string, body: object) =>
  get<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

const DemoContext = createContext<Store | null>(null);

export function DemoProvider({ children }: { children: ReactNode }) {
  const [withTalabat, setWithTalabat] = useState(false);
  const [method, setMethod] = useState<Method>('bank');
  const [mode, setMode] = useState<Mode>('rules');
  const [user, setUser] = useState<DemoUser>('main');
  const [withdrawals, setWithdrawals] = useState<HistoryItem[]>([]);
  const [added, setAdded] = useState<PastedSms[]>([]); // shortcut: memory only too, like withdrawals
  const [demo, setDemo] = useState<Demo | null>(null);
  const [inbox, setInbox] = useState<Sms[] | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [offlineMode, setOffline] = useState(false);
  const [reviewsChanged, setReviewsChanged] = useState(0); // bumped after a survey answer, so every tab reloads

  useEffect(() => {
    let cancelled = false;
    const withdrawn = withdrawals.reduce((sum, w) => sum + w.amount, 0);
    const extra = encodeURIComponent(JSON.stringify(added));
    setDemo(null);
    Promise.all([
      get<Demo>(
        `/demo?with_talabat=${withTalabat}&method=${method}&withdrawn=${withdrawn}&withdrawals=${withdrawals.length}` +
          `&extra=${extra}&mode=${mode}&user=${user}`,
      ),
      get<Sms[]>(`/inbox?with_talabat=${withTalabat}&extra=${extra}`),
      get<History>('/history'),
    ])
      .then(([d, i, h]) => {
        if (cancelled) return;
        setDemo(d);
        setInbox(i);
        setHistory(h);
        setOffline(false);
      })
      .catch((e) => {
        if (cancelled) return;
        console.warn(`Backend not reachable at "${API_URL}": ${e}. Showing offline demo.`);
        setDemo(offline.demo[`${user}_${mode}_${method}_${withTalabat}` as keyof typeof offline.demo] as Demo);
        setInbox(offline.inbox[`${withTalabat}`] as Sms[]);
        setHistory(offline.history as History);
        setOffline(true);
      });
    return () => {
      cancelled = true;
    };
  }, [withTalabat, method, mode, user, withdrawals, added, reviewsChanged]);

  const withdraw = (amount: number) =>
    setWithdrawals((w) => [{ type: 'withdrawal', date: history?.today ?? '', amount, method }, ...w]);

  const analyze = (sms: Omit<PastedSms, 'id'>) =>
    post<Analysis>('/analyze', {
      ...sms,
      added,
      with_talabat: withTalabat,
      method,
      withdrawn: withdrawals.reduce((sum, w) => sum + w.amount, 0),
      withdrawals: withdrawals.length,
      mode,
      user,
    });

  const reloadAfter = async (call: Promise<Review>) => {
    const review = await call;
    setReviewsChanged((n) => n + 1);
    return review;
  };

  return (
    <DemoContext.Provider
      value={{
        demo,
        inbox,
        history,
        offline: offlineMode,
        withTalabat,
        setWithTalabat,
        method,
        setMethod,
        mode,
        setMode,
        user,
        setUser: (u) => {
          setUser(u);
          setWithdrawals([]);
        },
        withdrawals,
        withdraw,
        added,
        addSms: (sms) => setAdded((a) => [...a, sms]),
        clearAdded: () => setAdded([]),
        analyze,
        submitSurvey: (answer) => reloadAfter(post<Review>('/survey', answer)),
        verifyPayment: (txId) => reloadAfter(post<Review>('/verify', { tx_id: txId })),
      }}>
      {children}
    </DemoContext.Provider>
  );
}

export function useDemo() {
  return useContext(DemoContext)!;
}

export const money = (x: number, decimals = 2) =>
  x.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

export const shortDate = (iso: string) =>
  new Date(iso.slice(0, 10) + 'T12:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
