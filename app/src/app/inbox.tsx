import { StyleSheet, View } from 'react-native';

import { Card, Chip, LABEL, Loading, Screen, Txt } from '@/components/finexa-ui';
import { ReviewBadge } from '@/components/identify-payment';
import { C, F } from '@/constants/theme';
import { money, shortDate, Sms, useDemo } from '@/demo-data';

const RULE_LABELS: Sms['label'][] = ['salary', 'gig_income', 'spending', 'ignore'];

export default function InboxScreen() {
  const { inbox } = useDemo();
  const counts = inbox?.reduce<Record<string, number>>((n, m) => ({ ...n, [m.label]: (n[m.label] ?? 0) + 1 }), {});

  return (
    <Screen title="Inbox" intro="The SMS Finexa read, and how it sorted each one. Only salary and gig income count.">
      {inbox && counts ? (
        <>
          <View style={s.summary}>
            {RULE_LABELS.map((k) => (
              <Chip key={k} label={`${LABEL[k].text} ${counts[k] ?? 0}`} color={LABEL[k].color} />
            ))}
          </View>
          {inbox.map((m) => (
            <Card key={m.id} style={{ gap: 8 }}>
              <View style={s.row}>
                <Txt style={s.sender}>{m.sender}</Txt>
                <Txt style={s.date}>{shortDate(m.date)}</Txt>
              </View>
              <Txt style={s.arabic}>{m.body}</Txt>
              <View style={s.row}>
                <Chip label={LABEL[m.label].text} color={LABEL[m.label].color} />
                {m.amount !== null && m.direction && (
                  <Txt style={[s.amount, { color: m.direction === 'in' ? C.green : C.muted }]}>
                    {m.direction === 'in' ? '+' : '−'}EGP {money(m.amount)}
                  </Txt>
                )}
              </View>
              {m.review && <ReviewBadge review={m.review} />}
            </Card>
          ))}
        </>
      ) : (
        <Loading />
      )}
    </Screen>
  );
}

const s = StyleSheet.create({
  summary: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  sender: { fontFamily: F.semibold, fontSize: 14 },
  date: { color: C.faint, fontSize: 12 },
  arabic: { fontFamily: F.arabic, fontSize: 15, lineHeight: 26, color: '#E4E4E7', textAlign: 'right', writingDirection: 'rtl' },
  amount: { fontFamily: F.semibold, fontSize: 14, fontVariant: ['tabular-nums'] },
});
