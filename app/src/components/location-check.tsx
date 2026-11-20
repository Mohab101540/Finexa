import * as Location from 'expo-location';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { Card, Txt } from '@/components/finexa-ui';
import { WorkMap } from '@/components/work-map';
import { C, F } from '@/constants/theme';
import { get } from '@/demo-data';
import {
  inWorkHours,
  isTracking,
  type Point,
  post,
  type Schedule,
  sendReadings,
  startTracking,
  stopTracking,
  toReading,
  type WorkSettings,
} from '@/work-tracking';

type Attendance = {
  status: 'ok' | 'needs_review' | 'not_enough_data' | 'skipped';
  reason: string;
  checks: number;
  last: { time: string; distance_m: number; inside: boolean } | null;
  work_hours_now: boolean;
};

const STATUS = {
  ok: { label: 'At work', color: C.green },
  needs_review: { label: 'Needs review', color: C.amber },
  not_enough_data: { label: 'Collecting', color: C.muted },
  skipped: { label: 'Off', color: C.muted },
};
export const RADII = [100, 200, 500, 1000];
export const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']; // index = the schedule's day number
export const hhmm = (h: number) => `${String((h + 24) % 24).padStart(2, '0')}:00`;

async function here(): Promise<Location.LocationObject> {
  if (!(await Location.requestForegroundPermissionsAsync()).granted) throw new Error('Location permission was not given.');
  return Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
}

export function LocationCheckCard() {
  const [settings, setSettings] = useState<WorkSettings | null>(null);
  const [attendance, setAttendance] = useState<Attendance | null>(null);
  const [you, setYou] = useState<Point | null>(null);
  const [tracking, setTracking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => setAttendance(await get<Attendance>('/attendance'));

  useEffect(() => {
    get<WorkSettings>('/workplace').then(setSettings).catch((e) => setError(String(e)));
    refresh().catch(() => {});
    isTracking().then(setTracking).catch(() => {});
    Location.getForegroundPermissionsAsync()
      .then(({ granted }) => (granted ? Location.getLastKnownPositionAsync() : null))
      .then((l) => l && setYou(toReading(l)))
      .catch(() => {});
  }, []);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const save = (next: WorkSettings) =>
    run(async () => {
      setSettings(await get<WorkSettings>('/workplace', post(next)));
      await refresh();
    });

  const setHere = () =>
    run(async () => {
      const r = toReading(await here());
      setYou(r);
      const base = settings ?? { radius_m: 200, schedule: { days: [0, 1, 2, 3, 4], start: '09:00', end: '17:00' } };
      setSettings(await get<WorkSettings>('/workplace', post({ ...base, workplace: r, remote: false })));
      await refresh();
    });

  const checkNow = () =>
    run(async () => {
      const r = toReading(await here());
      setYou(r);
      const saved = await sendReadings([r]);
      setNote(saved ? 'Reading sent.' : 'Outside your work hours, so nothing was sent.');
      await refresh();
    });

  const toggleTracking = () =>
    run(async () => {
      if (tracking) await stopTracking();
      else await startTracking();
      setTracking(await isTracking());
    });

  const workplace = settings?.workplace ?? null;
  const schedule: Schedule = settings?.schedule ?? { days: [0, 1, 2, 3, 4], start: '09:00', end: '17:00' };
  const edit = (change: Partial<WorkSettings>) => settings && workplace && save({ ...settings, ...change });
  const toggleDay = (d: number) => {
    const days = schedule.days.includes(d) ? schedule.days.filter((x) => x !== d) : [...schedule.days, d].sort();
    if (days.length) edit({ schedule: { ...schedule, days } });
  };
  const shift = (key: 'start' | 'end', by: number) =>
    edit({ schedule: { ...schedule, [key]: hhmm(Number(schedule[key].slice(0, 2)) + by) } });
  const status = attendance && STATUS[attendance.status];
  const nowAtWork = inWorkHours(new Date(), schedule);

  return (
    <Card style={{ gap: 12 }}>
      <View style={s.row}>
        <Txt style={s.title}>Work location</Txt>
        {status && <Txt style={[s.badge, { color: status.color, borderColor: status.color + '66' }]}>{status.label}</Txt>}
      </View>

      <WorkMap workplace={workplace} radius={settings?.radius_m ?? 200} you={you} />

      <Pressable accessibilityRole="button" disabled={busy} onPress={setHere} style={[s.button, s.secondary]}>
        <Txt style={s.buttonText}>{workplace ? 'Move workplace here' : 'Set workplace here'}</Txt>
      </Pressable>

      {workplace && (
        <>
          <Txt style={s.label}>Work radius</Txt>
          <View style={s.chips}>
            {RADII.map((r) => (
              <Chip key={r} on={settings?.radius_m === r} onPress={() => edit({ radius_m: r })}>
                {r < 1000 ? `${r} m` : '1 km'}
              </Chip>
            ))}
          </View>

          <Txt style={s.label}>Work days</Txt>
          <View style={s.chips}>
            {DAYS.map((name, d) => (
              <Chip key={name} on={schedule.days.includes(d)} onPress={() => toggleDay(d)}>
                {name}
              </Chip>
            ))}
          </View>

          <Txt style={s.label}>Work hours</Txt>
          <View style={s.row}>
            <Stepper value={schedule.start} onMinus={() => shift('start', -1)} onPlus={() => shift('start', 1)} />
            <Txt style={s.muted}>to</Txt>
            <Stepper value={schedule.end} onMinus={() => shift('end', -1)} onPlus={() => shift('end', 1)} />
          </View>

          <View style={s.row}>
            <Pressable accessibilityRole="button" disabled={busy} onPress={checkNow} style={[s.button, s.secondary]}>
              <Txt style={s.buttonText}>Check now</Txt>
            </Pressable>
            <Pressable
              accessibilityRole="switch"
              accessibilityState={{ checked: tracking }}
              disabled={busy}
              onPress={toggleTracking}
              style={[s.button, tracking ? s.secondary : s.primary]}>
              {busy ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Txt style={[s.buttonText, !tracking && { color: '#fff' }]}>
                  {tracking ? 'Stop background check' : 'Start background check'}
                </Txt>
              )}
            </Pressable>
          </View>

          <Txt style={s.muted}>
            {nowAtWork ? 'Work hours now: ' : 'Outside your work hours: '}
            {tracking
              ? nowAtWork
                ? 'Finexa reads your location about every 15 minutes.'
                : 'nothing is sent until your next shift.'
              : 'the background check is off.'}
          </Txt>
        </>
      )}

      {attendance && (
        <View style={{ gap: 4 }}>
          <Txt style={s.reason}>{attendance.reason}</Txt>
          {attendance.last && (
            <Txt style={[s.muted, { color: attendance.last.inside ? C.green : C.red }]}>
              Last check: {attendance.last.distance_m.toLocaleString()} m from work (
              {attendance.last.inside ? 'inside' : 'outside'} the work area)
            </Txt>
          )}
          <Txt style={s.muted}>This never stops a withdrawal. A weak record is only sent to a person for review.</Txt>
        </View>
      )}
      {note && <Txt style={s.muted}>{note}</Txt>}
      {error && <Txt style={[s.muted, { color: C.red }]}>{error}</Txt>}
    </Card>
  );
}

export function Chip({ on, onPress, children }: { on: boolean; onPress: () => void; children: string }) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked: on }}
      onPress={onPress}
      style={[s.chip, on && { backgroundColor: C.indigo, borderColor: C.indigo }]}>
      <Txt style={[s.chipText, on && { color: '#fff' }]}>{children}</Txt>
    </Pressable>
  );
}

export function Stepper({ value, onMinus, onPlus }: { value: string; onMinus: () => void; onPlus: () => void }) {
  return (
    <View style={s.stepper}>
      <Pressable accessibilityRole="button" accessibilityLabel={`Earlier than ${value}`} onPress={onMinus} style={s.step}>
        <Txt style={s.stepText}>−</Txt>
      </Pressable>
      <Txt style={s.stepValue}>{value}</Txt>
      <Pressable accessibilityRole="button" accessibilityLabel={`Later than ${value}`} onPress={onPlus} style={s.step}>
        <Txt style={s.stepText}>+</Txt>
      </Pressable>
    </View>
  );
}

const s = StyleSheet.create({
  title: { fontFamily: F.semibold, fontSize: 16 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  badge: { fontFamily: F.medium, fontSize: 12, borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 },
  label: { color: C.muted, fontSize: 12, fontFamily: F.medium, marginBottom: -4 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { borderColor: C.line, borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, minHeight: 36, justifyContent: 'center' },
  chipText: { fontFamily: F.medium, fontSize: 13 },
  stepper: { flex: 1, flexDirection: 'row', alignItems: 'center', borderColor: C.line, borderWidth: 1, borderRadius: 12 },
  step: { paddingHorizontal: 14, paddingVertical: 10, minWidth: 44, alignItems: 'center' },
  stepText: { fontFamily: F.semibold, fontSize: 18 },
  stepValue: { flex: 1, textAlign: 'center', fontFamily: F.semibold, fontSize: 15 },
  button: { flex: 1, borderRadius: 12, paddingVertical: 12, alignItems: 'center', justifyContent: 'center', minHeight: 46 },
  primary: { backgroundColor: C.indigo },
  secondary: { borderColor: C.line, borderWidth: 1 },
  buttonText: { fontFamily: F.semibold, fontSize: 14, textAlign: 'center' },
  reason: { fontSize: 14, lineHeight: 20 },
  muted: { color: C.muted, fontSize: 13, lineHeight: 19 },
});
