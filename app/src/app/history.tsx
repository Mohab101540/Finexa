import { StyleSheet, View } from 'react-native';

import { Card, Chip, Loading, Screen, SectionTitle, Txt } from '@/components/finexa-ui';
import { C, F } from '@/constants/theme';
import { HistoryItem, money, shortDate, useDemo } from '@/demo-data';

function Row({ item, pending }: { item: HistoryItem; pending?: boolean }) {
  const isWithdrawal = item.type === 'withdrawal';
  return (
    <Card style={s.row}>
      <View style={{ flex: 1, gap: 2 }}>
        <Txt style={s.rowTitle}>
          {isWithdrawal ? `Withdrawal to ${item.method === 'wallet' ? 'mobile wallet' : 'bank account'}` : 'Repaid on payday'}
        </Txt>
        <Txt style={s.rowDate}>{shortDate(item.date)}</Txt>
      </View>
      <View style={{ alignItems: 'flex-end', gap: 4 }}>
        <Txt style={s.rowAmount}>EGP {money(item.amount, 0)}</Txt>
        {pending && <Chip label="Due on payday" color={C.amber} />}
        {item.on_time && <Chip label="On time" color={C.green} />}
      </View>
    </Card>
  );
}

export default function HistoryScreen() {
  const { history, withdrawals } = useDemo();
  if (!history) return <Screen title="History"><Loading /></Screen>;

  const { on_time_streak: streak, next_tier: next, next_tier_streak: needed } = history;
  return (
    <Screen title="History">
      <Card style={{ gap: 12 }}>
        <Txt style={s.tierLine}>
          {next && needed
            ? `You're ${history.tier}. ${needed - streak} more on-time repayments to ${next}.`
            : `You're ${history.tier}, the highest tier.`}
        </Txt>
        {next && needed && (
          <>
            <View style={s.dots} accessibilityLabel={`${streak} of ${needed} on-time repayments`}>
              {Array.from({ length: needed }, (_, i) => (
                <View key={i} style={[s.dot, i < streak && s.dotOn]} />
              ))}
            </View>
            <Txt style={s.note}>
              {next} unlocks {history.next_tier_rate}% of what you've earned. One late repayment drops you a tier.
            </Txt>
          </>
        )}
      </Card>

      {withdrawals.length > 0 && (
        <>
          <SectionTitle>This cycle</SectionTitle>
          {withdrawals.map((w, i) => (
            <Row key={i} item={w} pending />
          ))}
        </>
      )}

      <SectionTitle>Earlier</SectionTitle>
      {history.items.map((item, i) => (
        <Row key={i} item={item} />
      ))}
    </Screen>
  );
}

const s = StyleSheet.create({
  tierLine: { fontFamily: F.semibold, fontSize: 17, lineHeight: 24 },
  dots: { flexDirection: 'row', gap: 6 },
  dot: { flex: 1, height: 8, borderRadius: 4, backgroundColor: C.line },
  dotOn: { backgroundColor: C.green },
  note: { color: C.muted, fontSize: 13, lineHeight: 19 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  rowTitle: { fontFamily: F.medium, fontSize: 15 },
  rowDate: { color: C.faint, fontSize: 12 },
  rowAmount: { fontFamily: F.semibold, fontSize: 15, fontVariant: ['tabular-nums'] },
});
