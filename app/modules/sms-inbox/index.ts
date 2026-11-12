import { requireNativeModule } from 'expo-modules-core';

export type RawSms = { id: string; sender: string; date: number; body: string };

export default requireNativeModule<{ readInbox(limit: number, sinceMs: number): Promise<RawSms[]> }>('SmsInbox');
