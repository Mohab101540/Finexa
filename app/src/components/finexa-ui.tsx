import { ReactNode } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextProps, View, ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { C, F } from '@/constants/theme';
import { MlLabel, Reason, useDemo } from '@/demo-data';

export const LABEL: Record<MlLabel | 'needs_review', { text: string; color: string }> = {
  salary: { text: 'Salary', color: C.green },
  gig_income: { text: 'Gig income', color: C.amber },
  spending: { text: 'Spending', color: C.red },
  ignore: { text: 'Ignored', color: C.faint },
  transfer_in: { text: 'Transfer in', color: C.indigo },
  transfer_out: { text: 'Transfer out', color: C.muted },
  needs_review: { text: 'Needs review', color: C.text },
};

export function Txt({ style, ...props }: TextProps) {
  return <Text style={[styles.body, style]} {...props} />;
}

export function Screen({ title, intro, children }: { title: string; intro?: string; children: ReactNode }) {
  const { offline } = useDemo();
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Txt style={styles.title} accessibilityRole="header">
            {title}
          </Txt>
          {offline && (
            <View style={styles.offline}>
              <Txt style={styles.offlineText}>Offline demo</Txt>
            </View>
          )}
        </View>
        {intro && <Txt style={styles.intro}>{intro}</Txt>}
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function Loading() {
  return <ActivityIndicator size="large" color={C.indigo} style={{ marginVertical: 64 }} />;
}

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <Txt style={styles.section}>{children}</Txt>;
}

const REASON_COLOR = { green: C.green, red: C.red, info: C.faint };

export function ReasonCard({ reason, highlight }: { reason: Reason; highlight?: boolean }) {
  return (
    <View
      style={[
        styles.reason,
        { borderLeftColor: highlight ? C.indigo : REASON_COLOR[reason.type] },
        highlight && styles.reasonHighlight,
      ]}>
      <Txt style={styles.reasonText}>{reason.en}</Txt>
    </View>
  );
}

export function Chip({ label, color }: { label: string; color: string }) {
  return (
    <View style={[styles.chip, { backgroundColor: color + '22', borderColor: color + '55' }]}>
      <Txt style={[styles.chipText, { color }]}>{label}</Txt>
    </View>
  );
}

export function Bar({ value, max, color = C.indigo }: { value: number; max: number; color?: string }) {
  const pct = Math.max(0, Math.min(1, max ? value / max : 1)) * 100;
  return (
    <View style={styles.barTrack}>
      <View style={[styles.barFill, { width: `${pct}%`, backgroundColor: color }]} />
    </View>
  );
}

export const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  content: { padding: 20, paddingBottom: 40, gap: 16, width: '100%', maxWidth: 560, alignSelf: 'center' },
  body: { color: C.text, fontFamily: F.regular, fontSize: 15, lineHeight: 22 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 },
  title: { fontFamily: F.bold, fontSize: 28, lineHeight: 34, letterSpacing: -0.5 },
  intro: { color: C.muted, fontSize: 14, lineHeight: 21, marginTop: -8 },
  offline: { backgroundColor: C.amber, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 },
  offlineText: { color: C.bg, fontFamily: F.semibold, fontSize: 12, lineHeight: 16 },
  card: { backgroundColor: C.surface, borderColor: C.line, borderWidth: 1, borderRadius: 20, padding: 16 },
  section: { fontFamily: F.semibold, fontSize: 16, marginTop: 8 },
  reason: {
    backgroundColor: C.surface,
    borderRadius: 12,
    borderLeftWidth: 3,
    paddingVertical: 12,
    paddingHorizontal: 14,
  },
  reasonHighlight: { backgroundColor: C.indigo + '1A' },
  reasonText: { fontSize: 14, lineHeight: 20 },
  chip: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 2, alignSelf: 'flex-start' },
  chipText: { fontFamily: F.medium, fontSize: 12, lineHeight: 18 },
  barTrack: { height: 8, borderRadius: 4, backgroundColor: C.line, overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: 4 },
});
