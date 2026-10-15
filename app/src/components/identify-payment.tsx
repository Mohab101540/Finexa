import Ionicons from '@expo/vector-icons/Ionicons';
import * as ImagePicker from 'expo-image-picker';
import { useState } from 'react';
import { Image, Modal, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';

import { Card, Chip, Txt } from '@/components/finexa-ui';
import { C, F } from '@/constants/theme';
import { money, Review, ReviewStatus, SurveyAnswer, useDemo } from '@/demo-data';

const ANSWERS: [string, string][] = [
  ['gig', 'Gig work or delivery earnings'],
  ['freelance', 'Freelance work or a client'],
  ['atm_cash', 'Cash earnings deposited through an ATM'],
  ['customer', 'Payment from a customer or business'],
  ['family', 'Transfer from a friend or family member'],
  ['own_accounts', 'Refund, savings, or transfer between my own accounts'],
  ['other', 'Something else'],
];
const EVIDENCE: [SurveyAnswer['evidence'], string][] = [
  ['now', 'I can submit proof now'],
  ['later', "I'll provide proof later"],
  ['none', "I don't have supporting documents"],
];
const STATUS:Record<ReviewStatus, { text: string; color: string }> = {
  needs_review: { text: 'Needs review', color: C.amber },
  user_reported: { text: 'Reported', color: C.indigo },
  awaiting_evidence: { text: 'Awaiting proof', color: C.indigo },
  verified: { text: 'Verified', color: C.green },
  flagged: { text: 'Flagged', color: C.red },
  reversed: { text: 'Reversed', color: C.faint },
};
const answerText = (key: string | null) => ANSWERS.find(([k]) => k === key)?.[1] ?? '—';

export function ReviewBadge({ review, onChanged }: { review: Review; onChanged?: (r: Review) => void }) {
  const [open, setOpen] = useState(false);
  const st = STATUS[review.status];
  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${st.text}: open payment details`}
        onPress={() => setOpen(true)}
        style={s.badge}>
        <Chip label={`${st.text}${review.remembered ? ' · remembered' : ''} ›`} color={st.color} />
      </Pressable>
      {review.flag_reason && <Txt style={[s.hint, { color: C.red }]}>{review.flag_reason}</Txt>}
      {open && <IdentifyPayment review={review} onClose={() => setOpen(false)} onChanged={onChanged} />}
    </>
  );
}

function Radio({ on, label, onPress }: { on: boolean; label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="radio" accessibilityState={{ checked: on }} onPress={onPress} style={s.radioRow}>
      <View style={[s.radio, on && s.radioOn]}>{on && <View style={s.radioDot} />}</View>
      <Txt style={s.radioText}>{label}</Txt>
    </Pressable>
  );
}

function IdentifyPayment({
  review,
  onClose,
  onChanged,
}: {
  review: Review;
  onClose: () => void;
  onChanged?: (r: Review) => void;
}) {
  const { submitSurvey, verifyPayment, offline } = useDemo();
  const [current, setCurrent] = useState(review);
  const [answer, setAnswer] = useState<string | null>(null);
  const [details, setDetails] = useState('');
  const [evidence, setEvidence] = useState<SurveyAnswer['evidence'] | null>(null);
  const [image, setImage] = useState<{ uri: string; base64: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const run = (call: Promise<Review>) => {
    setBusy(true);
    setError('');
    call
      .then((r) => {
        setCurrent(r);
        onChanged?.(r);
      })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const pickImage = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], base64: true, quality: 0.6 });
    const asset = res.canceled ? null : res.assets[0];
    if (asset?.base64) setImage({ uri: asset.uri, base64: asset.base64 });
  };

  const canSubmit = !busy && !offline && answer && evidence && (evidence !== 'now' || image);
  const submit = () =>
    run(
      submitSurvey({
        tx_id: current.tx_id,
        answer: answer!,
        details: details.trim(),
        evidence: evidence!,
        image: evidence === 'now' ? image?.base64 : undefined,
      }),
    );

  const st = STATUS[current.status];
  return (
    <Modal visible animationType="slide" onRequestClose={onClose}>
      <ScrollView style={{ backgroundColor: C.bg }} contentContainerStyle={s.page}>
        <View style={s.header}>
          <View style={s.icon}>
            <Ionicons name="wallet-outline" size={22} color={C.text} />
          </View>
          <View style={{ flex: 1 }}>
            <Txt style={s.title} accessibilityRole="header">
              Identify this payment
            </Txt>
            <Txt style={s.hint}>Incoming transaction detected</Txt>
          </View>
          <Chip label={st.text} color={st.color} />
        </View>

        <View style={s.amountBox}>
          <Txt style={s.hint}>Transaction amount</Txt>
          <Txt style={s.amount}>EGP {money(current.amount)}</Txt>
          <Txt style={s.hint}>
            {current.counterparty ? `From ${current.counterparty}` : 'Sender not named'} ·{' '}
            {current.answer ? answerText(current.answer) : 'Source not yet identified'}
          </Txt>
        </View>

        {current.status === 'flagged' && (
          <Card style={{ borderColor: C.red + '66', gap: 6 }}>
            <Txt style={[s.question, { color: C.red }]}>Flagged for review</Txt>
            <Txt style={s.body}>{current.flag_reason}</Txt>
            <Txt style={s.hint}>Flagged money never counts toward your limit.</Txt>
          </Card>
        )}

        {current.status === 'needs_review' && (
          <>
            <Txt style={s.question}>Where did this money come from?</Txt>
            <View accessibilityRole="radiogroup">
              {ANSWERS.map(([k, label]) => (
                <Radio key={k} on={answer === k} label={label} onPress={() => setAnswer(k)} />
              ))}
            </View>

            <Txt style={s.question}>Tell us a little more</Txt>
            <TextInput
              value={details}
              onChangeText={setDetails}
              placeholder="e.g. Payment for three delivery shifts, or a freelance design project…"
              placeholderTextColor={C.faint}
              multiline
              maxLength={500}
              style={s.input}
              accessibilityLabel="Tell us a little more"
            />

            <Txt style={s.question}>Supporting evidence</Txt>
            <View accessibilityRole="radiogroup">
              {EVIDENCE.map(([k, label]) => (
                <Radio key={k} on={evidence === k} label={label} onPress={() => setEvidence(k)} />
              ))}
            </View>
            {evidence === 'now' && (
              <View style={{ gap: 10 }}>
                <Pressable accessibilityRole="button" onPress={pickImage} style={s.secondary}>
                  <Txt style={s.secondaryText}>{image ? 'Choose another image' : 'Attach an image'}</Txt>
                </Pressable>
                {image && <Image source={{ uri: image.uri }} style={s.preview} accessibilityLabel="Attached proof" />}
              </View>
            )}

            <Pressable
              accessibilityRole="button"
              disabled={!canSubmit}
              onPress={submit}
              style={[s.primary, !canSubmit && { backgroundColor: C.line }]}>
              <Txt style={s.primaryText}>{busy ? 'Sending…' : 'Submit'}</Txt>
            </Pressable>
          </>
        )}

        {current.status !== 'needs_review' && current.status !== 'flagged' && (
          <Card style={{ gap: 6 }}>
            <Txt style={s.question}>Your answer</Txt>
            <Txt style={s.body}>{answerText(current.answer)}</Txt>
            {!!current.details && <Txt style={s.hint}>“{current.details}”</Txt>}
            {current.remembered && (
              <Txt style={s.hint}>Answered automatically: you already explained a payment from this sender.</Txt>
            )}
            <Txt style={s.hint}>
              {current.status === 'verified'
                ? 'Verified. Side income now counts toward your gig booster.'
                : 'Waiting for verification. It does not change your limit until it is verified.'}
            </Txt>
          </Card>
        )}

        {(current.status === 'user_reported' || current.status === 'awaiting_evidence') && (
          <View style={s.admin}>
            <Txt style={s.adminLabel}>DEMO ADMIN ACTION — not part of the user's app</Txt>
            <Pressable
              accessibilityRole="button"
              disabled={busy || offline}
              onPress={() => run(verifyPayment(current.tx_id))}
              style={s.adminButton}>
              <Txt style={s.adminButtonText}>Mark as verified</Txt>
            </Pressable>
          </View>
        )}

        {!!error && <Txt style={[s.hint, { color: C.red }]}>{error}</Txt>}

        <Pressable accessibilityRole="button" onPress={onClose} style={s.secondary}>
          <Txt style={s.secondaryText}>Close</Txt>
        </Pressable>
      </ScrollView>
    </Modal>
  );
}

const s = StyleSheet.create({
  badge: { alignSelf: 'flex-start' },
  page: { padding: 20, paddingTop: 48, paddingBottom: 48, gap: 16, width: '100%', maxWidth: 560, alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  icon: { width: 40, height: 40, borderRadius: 12, backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center' },
  title: { fontFamily: F.bold, fontSize: 20, lineHeight: 26 },
  hint: { color: C.muted, fontSize: 13, lineHeight: 19 },
  body: { fontSize: 15, lineHeight: 22 },
  amountBox: { backgroundColor: C.surface, borderRadius: 16, padding: 16, gap: 4 },
  amount: { fontFamily: F.bold, fontSize: 28, lineHeight: 36, fontVariant: ['tabular-nums'] },
  question: { fontFamily: F.semibold, fontSize: 16, marginTop: 4 },
  radioRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 9 },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: '#3F3F46', alignItems: 'center', justifyContent: 'center' },
  radioOn: { borderColor: C.indigo, backgroundColor: C.indigo },
  radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.text },
  radioText: { flex: 1, fontSize: 15 },
  input: {
    minHeight: 96,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 14,
    padding: 14,
    color: C.text,
    fontFamily: F.regular,
    fontSize: 15,
    textAlignVertical: 'top',
    backgroundColor: C.surface,
  },
  preview: { width: 120, height: 120, borderRadius: 12 },
  primary: { backgroundColor: C.indigo, borderRadius: 16, paddingVertical: 15, alignItems: 'center', marginTop: 8 },
  primaryText: { fontFamily: F.bold, fontSize: 15 },
  secondary: { borderColor: C.line, borderWidth: 1, borderRadius: 16, paddingVertical: 13, alignItems: 'center' },
  secondaryText: { fontFamily: F.semibold, fontSize: 15 },
  admin: { borderWidth: 1, borderStyle: 'dashed', borderColor: C.amber, borderRadius: 16, padding: 14, gap: 10 },
  adminLabel: { color: C.amber, fontFamily: F.semibold, fontSize: 12, letterSpacing: 0.5 },
  adminButton: { backgroundColor: C.amber + '22', borderRadius: 12, paddingVertical: 12, alignItems: 'center' },
  adminButtonText: { color: C.amber, fontFamily: F.bold, fontSize: 15 },
});
