import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { errorText, useAuth } from '@/auth';
import { Card, Txt } from '@/components/finexa-ui';
import { Chip, DAYS, hhmm, RADII, Stepper } from '@/components/location-check';
import { WorkMap } from '@/components/work-map';
import { C, F } from '@/constants/theme';
import { get } from '@/demo-data';
import { post, type Point, type Schedule, type WorkSettings } from '@/work-tracking';

type Kind = 'id_front' | 'id_back' | 'selfie' | 'income_proof' | 'remote_proof';
export type Progress = {
  status: 'incomplete' | 'needs_review' | 'verified';
  steps: Record<string, boolean>;
  missing: string[];
  remote: boolean;
  national_id: { last4: string; birth_date: string; governorate: string; gender: string } | null;
  face: { status: string; score: number | null; reason: string } | null;
  notes: string[];
};
type Step = 'id' | 'selfie' | 'work' | 'income' | 'done';
const STEPS: { key: Step; title: string }[] = [
  { key: 'id', title: 'National ID' },
  { key: 'selfie', title: 'Selfie' },
  { key: 'work', title: 'Work' },
  { key: 'income', title: 'Proof of income' },
  { key: 'done', title: 'Review' },
];
const UPLOAD_MS = 60_000; // photos are big: allow a minute instead of the usual 8 seconds
const DEFAULT_SCHEDULE: Schedule = { days: [0, 1, 2, 3, 4], start: '09:00', end: '17:00' };

export const STATUS_TEXT = {
  incomplete: { label: 'Sign-up not finished', color: C.amber },
  needs_review: { label: 'Waiting for review', color: '#A5B4FC' },
  verified: { label: 'Verified', color: C.green },
};

export function OnboardingScreen() {
  const { setOnboarding } = useAuth();
  const [step, setStep] = useState<Step>('id');
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Progress>('/onboarding').then(setProgress).catch((e) => setError(errorText(e)));
  }, []);

  const index = STEPS.findIndex((s) => s.key === step);
  const next = () => setStep(STEPS[Math.min(index + 1, STEPS.length - 1)].key);

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
        <View style={s.row}>
          <Txt style={s.title}>Finish signing up</Txt>
          <Pressable accessibilityRole="button" onPress={() => setOnboarding(false)}>
            <Txt style={s.link}>Do this later</Txt>
          </Pressable>
        </View>
        <View style={s.tabs}>
          {STEPS.map((t, i) => (
            <Pressable
              key={t.key}
              accessibilityRole="tab"
              accessibilityState={{ selected: t.key === step }}
              onPress={() => setStep(t.key)}
              style={[s.tab, t.key === step && s.tabOn]}>
              <Txt style={[s.tabNumber, t.key === step && { color: '#fff' }]}>{i + 1}</Txt>
            </Pressable>
          ))}
        </View>
        <Txt style={s.stepTitle}>{STEPS[index].title}</Txt>

        {progress && step === 'id' && <IdStep progress={progress} onChange={setProgress} />}
        {progress && step === 'selfie' && <SelfieStep progress={progress} onChange={setProgress} />}
        {progress && step === 'work' && <WorkStep onChange={() => get<Progress>('/onboarding').then(setProgress)} />}
        {progress && step === 'income' && <IncomeStep progress={progress} onChange={setProgress} />}
        {progress && step === 'done' && <DoneStep progress={progress} onFinish={() => setOnboarding(false)} />}
        {!progress && !error && <ActivityIndicator color={C.indigo} style={{ marginTop: 40 }} />}
        {error && <Txt style={s.error}>{error}</Txt>}

        {step !== 'done' && (
          <Pressable accessibilityRole="button" onPress={next} style={s.primary}>
            <Txt style={s.primaryText}>Next</Txt>
          </Pressable>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

type StepProps = { progress: Progress; onChange: (p: Progress) => void };

function PhotoSlot({ kind, label, hint, done, onChange }: { kind: Kind; label: string; hint: string; done: boolean; onChange: (p: Progress) => void }) {
  const [uri, setUri] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selfie = kind === 'selfie';

  async function take(fromGallery: boolean) {
    setError(null);
    try {
      const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 1 };
      let res: ImagePicker.ImagePickerResult;
      if (fromGallery) res = await ImagePicker.launchImageLibraryAsync(options);
      else {
        if (!(await ImagePicker.requestCameraPermissionsAsync()).granted) throw new Error('Camera permission was not given.');
        res = await ImagePicker.launchCameraAsync({ ...options, cameraType: selfie ? ImagePicker.CameraType.front : ImagePicker.CameraType.back });
      }
      const asset = res.canceled ? null : res.assets[0];
      if (!asset) return;
      setUri(asset.uri);
      setBusy(true);
      const wide = asset.width >= asset.height;
      const ref = await ImageManipulator.manipulate(asset.uri)
        .resize(wide ? { width: Math.min(asset.width, 1600) } : { height: Math.min(asset.height, 1600) })
        .renderAsync();
      const small = await ref.saveAsync({ base64: true, compress: 0.7, format: SaveFormat.JPEG });
      onChange(await get<Progress>('/onboarding/document', post({ kind, image: small.base64 }), UPLOAD_MS));
    } catch (e) {
      setUri(null);
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card style={{ gap: 10 }}>
      <View style={s.row}>
        <Txt style={s.slotTitle}>{label}</Txt>
        {done && !busy && <Txt style={s.done}>✓ Sent</Txt>}
      </View>
      <Txt style={s.hint}>{hint}</Txt>
      {uri && <Image source={{ uri }} style={[s.preview, selfie && s.selfiePreview]} resizeMode="cover" />}
      <View style={s.row}>
        <Pressable accessibilityRole="button" disabled={busy} onPress={() => take(false)} style={[s.button, s.buttonPrimary]}>
          {busy ? <ActivityIndicator color="#fff" /> : <Txt style={s.buttonTextLight}>{selfie ? 'Take a selfie' : 'Take a photo'}</Txt>}
        </Pressable>
        {!selfie && (
          <Pressable accessibilityRole="button" disabled={busy} onPress={() => take(true)} style={[s.button, s.buttonGhost]}>
            <Txt style={s.buttonText}>From gallery</Txt>
          </Pressable>
        )}
      </View>
      {error && <Txt style={s.error}>{error}</Txt>}
    </Card>
  );
}

function IdStep({ progress, onChange }: StepProps) {
  const [number, setNumber] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = progress.national_id;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onChange(await get<Progress>('/onboarding/national-id', post({ number })));
      setNumber('');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card style={{ gap: 10 }}>
        <Txt style={s.slotTitle}>National ID number</Txt>
        <Txt style={s.hint}>The 14 digits on your card. Finexa checks they match a real birth date and governorate.</Txt>
        {id && (
          <Txt style={s.done}>
            ✓ …{id.last4} · born {id.birth_date} · {id.governorate}
          </Txt>
        )}
        <View style={s.row}>
          <TextInput
            style={s.input}
            value={number}
            onChangeText={setNumber}
            keyboardType="number-pad"
            maxLength={14}
            placeholder={id ? 'Change the number' : '14 digits'}
            placeholderTextColor={C.faint}
          />
          <Pressable accessibilityRole="button" disabled={busy || number.length < 14} onPress={save} style={[s.button, s.buttonPrimary, { flex: 0, paddingHorizontal: 18 }, number.length < 14 && { backgroundColor: C.line }]}>
            {busy ? <ActivityIndicator color="#fff" /> : <Txt style={s.buttonTextLight}>Save</Txt>}
          </Pressable>
        </View>
        {error && <Txt style={s.error}>{error}</Txt>}
      </Card>
      <PhotoSlot kind="id_front" label="Front of the ID" hint="The side with your photo. Lay the card flat, all four corners in the picture, no glare." done={progress.steps.id_front} onChange={onChange} />
      <PhotoSlot kind="id_back" label="Back of the ID" hint="The side with your address and job." done={progress.steps.id_back} onChange={onChange} />
    </>
  );
}

function SelfieStep({ progress, onChange }: StepProps) {
  const face = progress.face;
  return (
    <>
      <PhotoSlot
        kind="selfie"
        label="Your face"
        hint="Look straight at the camera in good light, no sunglasses or hat. Finexa compares it with the photo on your ID."
        done={progress.steps.selfie}
        onChange={onChange}
      />
      {face && (
        <Card style={{ gap: 6, borderColor: (face.status === 'match' ? C.green : C.amber) + '66' }}>
          <Txt style={[s.slotTitle, { color: face.status === 'match' ? C.green : C.amber }]}>
            {face.status === 'match' ? 'Face matches your ID' : 'Face check needs a person'}
          </Txt>
          <Txt style={s.hint}>
            {face.reason}
            {face.score !== null && ` Similarity ${face.score.toFixed(2)} (a match is 0.36 or more).`} A reviewer always
            looks at it too, because an ID photo can be old or small.
          </Txt>
        </Card>
      )}
    </>
  );
}

function WorkStep({ onChange }: { onChange: () => void }) {
  const [settings, setSettings] = useState<WorkSettings | null>(null);
  const [pin, setPin] = useState<Point | null>(null);
  const [remote, setRemote] = useState(false);
  const [radius, setRadius] = useState(200);
  const [schedule, setSchedule] = useState<Schedule>(DEFAULT_SCHEDULE);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<WorkSettings>('/workplace')
      .then((w) => {
        setSettings(w);
        setPin(w.workplace);
        setRemote(w.remote);
        setRadius(w.radius_m);
        setSchedule(w.schedule);
      })
      .catch((e) => setError(errorText(e)));
  }, []);

  async function useHere() {
    setError(null);
    try {
      if (!(await Location.requestForegroundPermissionsAsync()).granted) throw new Error('Location permission was not given.');
      const l = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      setPin({ lat: l.coords.latitude, lon: l.coords.longitude });
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const night_check = settings?.night_check ?? false; // keep the night-check consent if it was given before
      const body = remote ? { workplace: null, remote: true, radius_m: radius, schedule } : { workplace: pin, remote: false, radius_m: radius, schedule, night_check };
      setSettings(await get<WorkSettings>('/workplace', post(body)));
      setNote('Saved.');
      if (!remote) {
        const { checks } = await get<{ checks: { key: string; reason: string }[] }>(
          '/workplace/checks', post({ messages: [] }), 30_000).catch(() => ({ checks: [] }));
        const place = checks.find((c) => c.key === 'place');
        if (place) setNote(`Saved. ${place.reason}`);
      }
      onChange();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const toggleDay = (d: number) => {
    const days = schedule.days.includes(d) ? schedule.days.filter((x) => x !== d) : [...schedule.days, d].sort();
    if (days.length) setSchedule({ ...schedule, days });
  };
  const shift = (key: 'start' | 'end', by: number) => setSchedule({ ...schedule, [key]: hhmm(Number(schedule[key].slice(0, 2)) + by) });

  return (
    <Card style={{ gap: 12 }}>
      <View style={s.segment}>
        {[false, true].map((r) => (
          <Pressable key={String(r)} accessibilityRole="radio" accessibilityState={{ checked: remote === r }} onPress={() => setRemote(r)} style={[s.segmentItem, remote === r && s.segmentOn]}>
            <Txt style={[s.segmentText, remote !== r && { color: C.faint }]}>{r ? 'I work remotely' : 'I work at a workplace'}</Txt>
          </Pressable>
        ))}
      </View>

      {remote ? (
        <Txt style={s.hint}>
          No location check for remote workers. Instead, the next step asks for proof that you work remotely, and your
          limit relies on your salary SMS.
        </Txt>
      ) : (
        <>
          <Txt style={s.hint}>Tap the map where you work, or use your location if you are there now. During your work hours Finexa checks that your phone is inside this circle.</Txt>
          <WorkMap workplace={pin} radius={radius} you={null} onPick={setPin} />
          <Pressable accessibilityRole="button" onPress={useHere} style={[s.button, s.buttonGhost]}>
            <Txt style={s.buttonText}>I am at work now: use my location</Txt>
          </Pressable>
          <Txt style={s.label}>Work radius</Txt>
          <View style={s.chips}>
            {RADII.map((r) => (
              <Chip key={r} on={radius === r} onPress={() => setRadius(r)}>
                {r < 1000 ? `${r} m` : '1 km'}
              </Chip>
            ))}
          </View>
        </>
      )}

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
        <Txt style={s.hint}>to</Txt>
        <Stepper value={schedule.end} onMinus={() => shift('end', -1)} onPlus={() => shift('end', 1)} />
      </View>

      <Pressable accessibilityRole="button" disabled={busy || (!remote && !pin)} onPress={save} style={[s.button, s.buttonPrimary, !remote && !pin && { backgroundColor: C.line }]}>
        {busy ? <ActivityIndicator color="#fff" /> : <Txt style={s.buttonTextLight}>{settings?.workplace || settings?.remote ? 'Save changes' : 'Save'}</Txt>}
      </Pressable>
      {note && <Txt style={s.done}>{note}</Txt>}
      {error && <Txt style={s.error}>{error}</Txt>}
    </Card>
  );
}

function IncomeStep({ progress, onChange }: StepProps) {
  return (
    <>
      <PhotoSlot
        kind="income_proof"
        label="Proof of income"
        hint="Best: an HR letter from your employer with your name, job and monthly net salary, stamped or signed. No HR letter? A recent payslip or a bank statement showing your salary. Finexa also checks that this salary really arrives in your SMS."
        done={progress.steps.income_proof}
        onChange={onChange}
      />
      {progress.remote && (
        <PhotoSlot
          kind="remote_proof"
          label="Proof of remote work"
          hint="One of: your contract or HR letter saying the job is remote, a screenshot of your time tracker or timesheet, or your company portal, showing your name and recent dates."
          done={!!progress.steps.remote_proof}
          onChange={onChange}
        />
      )}
      {!progress.remote && <Txt style={s.hint}>Working remotely? Choose "I work remotely" in step 3 and a second upload appears here.</Txt>}
    </>
  );
}

const STEP_NAMES: Record<string, string> = {
  national_id: 'National ID number',
  id_front: 'Front of the ID',
  id_back: 'Back of the ID',
  selfie: 'Selfie',
  work: 'Workplace or remote work',
  income_proof: 'Proof of income',
  remote_proof: 'Proof of remote work',
};

function DoneStep({ progress, onFinish }: { progress: Progress; onFinish: () => void }) {
  const status = STATUS_TEXT[progress.status];
  return (
    <>
      <Card style={{ gap: 10 }}>
        <Txt style={[s.slotTitle, { color: status.color }]}>{status.label}</Txt>
        {Object.entries(progress.steps).map(([k, ok]) => (
          <Txt key={k} style={[s.hint, { color: ok ? C.green : C.amber }]}>
            {ok ? '✓' : '○'} {STEP_NAMES[k]}
          </Txt>
        ))}
        {progress.notes.map((n, i) => (
          <Txt key={i} style={s.hint}>
            {n}
          </Txt>
        ))}
        <Txt style={s.hint}>
          {progress.status === 'incomplete'
            ? 'You can look around now and finish later from Home.'
            : 'A person checks your documents next. You can already see your limit.'}
        </Txt>
      </Card>
      <Pressable accessibilityRole="button" onPress={onFinish} style={s.primary}>
        <Txt style={s.primaryText}>Go to Finexa</Txt>
      </Pressable>
    </>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  content: { padding: 20, paddingTop: 24, gap: 14 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  title: { fontFamily: F.bold, fontSize: 24 },
  link: { color: '#A5B4FC', fontFamily: F.semibold, fontSize: 14 },
  tabs: { flexDirection: 'row', gap: 8 },
  tab: { flex: 1, borderColor: C.line, borderWidth: 1, borderRadius: 10, paddingVertical: 8, alignItems: 'center' },
  tabOn: { backgroundColor: C.indigo, borderColor: C.indigo },
  tabNumber: { fontFamily: F.semibold, fontSize: 14, color: C.muted },
  stepTitle: { fontFamily: F.semibold, fontSize: 18, marginTop: 4 },
  slotTitle: { fontFamily: F.semibold, fontSize: 15 },
  hint: { color: C.muted, fontSize: 13, lineHeight: 19 },
  label: { color: C.muted, fontSize: 12, fontFamily: F.medium, marginBottom: -4 },
  done: { color: C.green, fontFamily: F.semibold, fontSize: 13 },
  error: { color: C.red, fontSize: 13, lineHeight: 19 },
  preview: { width: '100%', height: 160, borderRadius: 10, backgroundColor: C.surface },
  selfiePreview: { width: 140, height: 180, alignSelf: 'center' },
  input: { flex: 1, backgroundColor: C.bg, borderColor: C.line, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, color: C.text, fontFamily: F.regular, fontSize: 16, letterSpacing: 1 },
  button: { flex: 1, borderRadius: 12, paddingVertical: 12, alignItems: 'center', justifyContent: 'center', minHeight: 46 },
  buttonPrimary: { backgroundColor: C.indigo },
  buttonGhost: { borderColor: C.line, borderWidth: 1 },
  buttonText: { fontFamily: F.semibold, fontSize: 14 },
  buttonTextLight: { fontFamily: F.semibold, fontSize: 14, color: '#fff' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  segment: { flexDirection: 'row', backgroundColor: C.bg, borderColor: C.line, borderWidth: 1, borderRadius: 14, padding: 4 },
  segmentItem: { flex: 1, borderRadius: 10, paddingVertical: 10, alignItems: 'center', borderWidth: 1, borderColor: 'transparent' },
  segmentOn: { backgroundColor: C.surface, borderColor: '#3F3F46' },
  segmentText: { fontFamily: F.semibold, fontSize: 13 },
  primary: { backgroundColor: C.indigo, borderRadius: 16, paddingVertical: 15, alignItems: 'center', marginTop: 4 },
  primaryText: { fontFamily: F.bold, fontSize: 15, color: '#fff' },
});
