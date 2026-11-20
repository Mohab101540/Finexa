import { createContext, ReactNode, useContext, useState } from 'react';

import { get, setToken } from '@/demo-data';

export type Account = {
  id: number;
  phone: string;
  name: string;
  hr_salary: number | null; // as typed at sign-up, not verified yet
  employer: string | null;
  method: 'bank' | 'wallet';
};
export type SignupForm = {
  name: string;
  phone: string;
  password: string;
  hr_salary: number | null;
  employer: string | null;
  method: 'bank' | 'wallet';
};

type Auth = {
  account: Account | null; // null = not signed in
  demoOnly: boolean; // chose "Explore the demo" without an account
  onboarding: boolean; // showing the sign-up steps (ID, selfie, work, proof of income)
  setOnboarding: (on: boolean) => void;
  login: (phone: string, password: string) => Promise<void>;
  signup: (form: SignupForm) => Promise<void>;
  logout: () => void; // back to the account screen
  exploreDemo: () => void;
};

const post = (body: object): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [demoOnly, setDemoOnly] = useState(false);
  const [onboarding, setOnboarding] = useState(false);

  const login = async (phone: string, password: string) => {
    const res = await get<{ token: string; user: Account }>('/login', post({ phone, password }));
    setToken(res.token);
    const progress = await get<{ status: string }>('/onboarding').catch(() => null);
    setOnboarding(progress?.status === 'incomplete');
    setAccount(res.user);
  };

  return (
    <AuthContext.Provider
      value={{
        account,
        demoOnly,
        onboarding,
        setOnboarding,
        login,
        signup: async (form) => {
          await get<Account>('/signup', post(form));
          await login(form.phone, form.password);
        },
        logout: () => {
          setToken(null);
          setAccount(null);
          setDemoOnly(false);
          setOnboarding(false);
        },
        exploreDemo: () => setDemoOnly(true),
      }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext)!;
}

export function errorText(e: unknown) {
  const raw = e instanceof Error ? e.message : String(e);
  if (raw.includes('Aborted') || raw.includes('Network request failed')) return 'Cannot reach Finexa. Is `npm run demo` running?';
  try {
    const detail = JSON.parse(raw);
    if (Array.isArray(detail)) {
      const field = detail[0]?.loc?.at(-1);
      return FIELD_HELP[field] ?? `Check ${field}.`;
    }
    return typeof detail === 'string' ? detail.charAt(0).toUpperCase() + detail.slice(1) + '.' : raw;
  } catch {
    return raw;
  }
}

const FIELD_HELP: Record<string, string> = {
  phone: 'Enter an Egyptian mobile number: 11 digits starting with 010, 011, 012 or 015.',
  password: 'The password needs at least 8 characters.',
  name: 'Enter your name.',
  hr_salary: 'Enter your monthly net salary in EGP, or leave it empty.',
  employer: 'The employer name is too long.',
};
