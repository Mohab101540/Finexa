import * as Location from 'expo-location';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { Card, Txt } from '@/components/finexa-ui';
import { C, F } from '@/constants/theme';
import { get } from '@/demo-data';

type Point = { lat: number; lon: number; time: string };
type Check = { status: 'passed' | 'failed' | 'skipped'; reason: string; distance_m: number | null };

const STATUS_COLOR = { passed: C.green, failed: C.red, skipped: C.muted };

async function readPosition(): Promise<Point> {
  const { granted } = await Location.requestForegroundPermissionsAsync();
  if (!granted) throw new Error('Location permission was not given.');
  const { coords, timestamp } = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
  return { lat: coords.latitude, lon: coords.longitude, time: new Date(timestamp).toISOString() };
}

export function LocationCheckCard() {
  const [workplace, setWorkplace] = useState<Point | null>(null);
  const [previous, setPrevious] = useState<Point | null>(null);
  const [check, setCheck] = useState<Check | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: (here: Point) => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action(await readPosition());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const setHere = () =>
    run(async (here) => {
      setWorkplace(here);
      setPrevious(null);
      setCheck(null);
    });

  const checkNow = () =>
    run(async (here) => {
      const body = JSON.stringify({ location: here, workplace, previous });
      setCheck(await get<Check>('/location-check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body }));
      setPrevious(here);
    });

  return (
    <Card style={{ gap: 10 }}>
      <Txt style={s.title}>Workplace check</Txt>
      <Txt style={s.hint}>
        {workplace
          ? 'Workplace saved. A withdrawal needs the phone within 200 m of it, with no fake GPS jumps.'
          : 'For the demo, save where you are now as the workplace (real users get it from their HR letter).'}
      </Txt>
      <View style={s.row}>
        <Pressable accessibilityRole="button" disabled={busy} onPress={setHere} style={[s.button, s.secondary]}>
          <Txt style={s.secondaryText}>{workplace ? 'Move workplace here' : 'Set workplace here'}</Txt>
        </Pressable>
        <Pressable accessibilityRole="button" disabled={busy} onPress={checkNow} style={[s.button, s.primary]}>
          {busy ? <ActivityIndicator color="#fff" /> : <Txt style={s.primaryText}>Check my location</Txt>}
        </Pressable>
      </View>
      {check && (
        <Txt style={[s.result, { color: STATUS_COLOR[check.status] }]}>
          {check.status === 'passed' ? '✓ ' : check.status === 'failed' ? '✕ ' : ''}
          {check.reason}
        </Txt>
      )}
      {error && <Txt style={[s.hint, { color: C.red }]}>{error}</Txt>}
    </Card>
  );
}

const s = StyleSheet.create({
  title: { fontFamily: F.semibold, fontSize: 16 },
  hint: { color: C.muted, fontSize: 13, lineHeight: 19 },
  row: { flexDirection: 'row', gap: 8 },
  button: { flex: 1, borderRadius: 12, paddingVertical: 12, alignItems: 'center', justifyContent: 'center' },
  primary: { backgroundColor: C.indigo },
  primaryText: { color: '#fff', fontFamily: F.semibold, fontSize: 14 },
  secondary: { borderColor: C.line, borderWidth: 1 },
  secondaryText: { fontFamily: F.semibold, fontSize: 14 },
  result: { fontFamily: F.medium, fontSize: 14, lineHeight: 20 },
});
