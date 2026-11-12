import { PermissionsAndroid, Platform } from 'react-native';

export type PhoneSms = { id: string; sender: string; date: string; body: string };

const pad = (n: number) => String(n).padStart(2, '0');

const localIso = (ms: number) => {
  const d = new Date(ms);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

export async function readPhoneSms(limit = 60, days = 90): Promise<PhoneSms[]> {
  if (Platform.OS !== 'android') throw new Error('Reading SMS only works on an Android phone.');
  const answer = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.READ_SMS, {
    title: 'Let Finexa read your SMS?',
    message: 'Finexa looks for your salary and side income in your bank and wallet messages. Nothing is sent without you pressing the button.',
    buttonPositive: 'Allow',
    buttonNegative: 'Not now',
  });
  if (answer !== PermissionsAndroid.RESULTS.GRANTED) throw new Error('SMS permission was not allowed.');
  const SmsInbox = require('../modules/sms-inbox').default;
  const rows: { id: string; sender: string; date: number; body: string }[] = await SmsInbox.readInbox(
    limit,
    Date.now() - days * 86_400_000,
  );
  return rows
    .filter((r) => r.body.trim())
    .map((r) => ({ id: `phone-${r.id}`, sender: r.sender || 'Unknown', date: localIso(r.date), body: r.body.slice(0, 1000) }));
}
