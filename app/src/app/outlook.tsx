import { StyleSheet, View } from 'react-native';

import { Bar, Card, Loading, Screen, SectionTitle, Txt } from '@/components/finexa-ui';
import { C, F } from '@/constants/theme';
import { BAND_COLOR, Health, money, shortDate, useDemo } from '@/demo-data';

const BLOCKED = {
  no_salary_seen: 'No salary deposit seen in your SMS yet, so nothing can be withdrawn.',
  unpaid_last_cycle: "Last cycle's balance is still unpaid, so nothing can be withdrawn until it's settled.",
  salary_overdue: 'Your salary is more than 5 days overdue, so withdrawals pause until it arrives.',
};

function Step({ n, title, formula, result }: { n: number; title: string; formula: string; result: string }) {
  return (
    <View style={s.step}>
      <View style={s.stepNum}>
        <Txt style={s.stepNumText}>{n}</Txt>
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <View style={s.stepHead}>
          <Txt style={s.stepTitle}>{title}</Txt>
          <Txt style={s.stepResult}>{result}</Txt>
        </View>
        <Txt style={s.formula}>{formula}</Txt>
      </View>
    </View>
  );
}

function HealthSection({ h }: { h: Health }) {
  const top = h.categories[0]?.egp ?? 0;
  return (
    <>
      <SectionTitle>Financial health</SectionTitle>
      <Card style={{ gap: 12 }}>
        <View style={s.stepHead}>
          <Txt style={[s.boosterLine, { color: BAND_COLOR[h.band] }]}>{h.band}</Txt>
          <Txt style={s.stepResult}>{h.score} / 100</Txt>
        </View>
        <Txt style={s.note}>Coaching only: your health score never changes how much you can withdraw.</Txt>
      </Card>
      <Card style={{ gap: 12 }}>
        <Txt style={s.stepTitle}>Spending by category, 30 days to {shortDate(h.window_end)}</Txt>
        {h.categories.map((cat) => (
          <View key={cat.key} style={{ gap: 6 }}>
            <View style={s.barRow}>
              <Txt style={s.barLabel}>{cat.label}</Txt>
              <Txt style={s.barValue}>EGP {money(cat.egp, 0)}</Txt>
            </View>
            <Bar value={cat.egp} max={top} />
          </View>
        ))}
        {!h.categories.length && <Txt style={s.formula}>No spending in the last 30 days.</Txt>}
        <Txt style={s.note}>Total EGP {money(h.spent_30d, 0)}. Money that went straight back out and Finexa repayments are left out.</Txt>
      </Card>
      <Card style={{ gap: 16 }}>
        {h.factors.map((f) => (
          <View key={f.key} style={{ gap: 2 }}>
            <View style={s.stepHead}>
              <Txt style={s.stepTitle}>{f.label}</Txt>
              <Txt style={s.stepResult}>
                {f.points} / {f.max}
              </Txt>
            </View>
            <Txt style={s.formula}>{f.reason}</Txt>
          </View>
        ))}
      </Card>
      <Card style={s.tipCard}>
        <View style={s.stepHead}>
          <Txt style={s.stepTitle}>How to raise your score</Txt>
          {h.tip.gain > 0 && <Txt style={s.tipGain}>+{h.tip.gain} points</Txt>}
        </View>
        <Txt style={s.tipText}>{h.tip.text}</Txt>
      </Card>
    </>
  );
}

export default function OutlookScreen() {
  const { demo } = useDemo();
  if (!demo) return <Screen title="Outlook"><Loading /></Screen>;

  const c = demo.calc;
  if (c.blocked) {
    return (
      <Screen title="Outlook">
        <Card>
          <Txt>{BLOCKED[c.blocked]}</Txt>
        </Card>
        <HealthSection h={demo.health} />

      </Screen>
    );
  }

  const tierCap = c.cap / (1 + (c.booster_points * 2) / 100);
  const byRate = (c.earned * c.rate) / 100;
  const next = demo.booster_next;

  return (
    <Screen title="Outlook" intro="How today's amount is worked out, step by step.">
      <Card style={{ gap: 18 }}>
        <Step
          n={1}
          title="Salary used"
          formula={`Lower of HR letter (${money(c.hr_salary, 0)}) and median of last deposits (${c.salary_deposits
            .map((d) => money(d, 0))
            .join(', ')})`}
          result={money(c.salary_used, 0)}
        />
        <Step
          n={2}
          title="Days passed"
          formula={`Since payday on ${shortDate(c.last_payday)}, out of ${c.days_in_cycle} days in the cycle`}
          result={`${c.days_passed} / ${c.days_in_cycle}`}
        />
        <Step
          n={3}
          title="Earned"
          formula={`${money(c.salary_used, 0)} × ${c.days_passed} ÷ ${c.days_in_cycle}`}
          result={money(c.earned)}
        />
        <Step
          n={4}
          title="Rate"
          formula={`${c.rate_source === 'ai' ? `AI model ${c.base_rate}%` : `${c.tier} ${c.tier_rate}%`} + booster ${c.booster_points} ${c.wallet_adjustment ? `− wallet ${-c.wallet_adjustment}` : '+ bank 0'}`}
          result={`${c.rate}%`}
        />
        <Step
          n={5}
          title="Cap"
          formula={`${money(tierCap, 0)} × (1 + ${c.booster_points} × 2 ÷ 100)`}
          result={money(c.cap, 0)}
        />
        <Step
          n={6}
          title="Available"
          formula={`Lower of ${money(byRate)} (${c.rate}% of earned) and the cap, − withdrawn ${money(c.withdrawn, 0)} − fee ${money(c.fee, 0)}`}
          result={money(c.available)}
        />
      </Card>

      <SectionTitle>Gig booster</SectionTitle>
      <Card style={{ gap: 12 }}>
        <Txt style={s.boosterLine}>
          {c.booster_points ? `+${c.booster_points}% from ${c.gig_apps.join(', ')} income` : 'No booster yet'}
        </Txt>
        {next ? (
          <>
            <Txt style={s.formula}>
              Next level +{next.points}%: EGP {money(next.egp, 0)} of gig income across {next.weeks} different weeks, in
              the last 30 days.
            </Txt>
            <View style={s.barRow}>
              <Txt style={s.barLabel}>Gig income</Txt>
              <Txt style={s.barValue}>
                {money(c.gig_income_30d, 0)} / {money(next.egp, 0)}
              </Txt>
            </View>
            <Bar value={c.gig_income_30d} max={next.egp} color={C.amber} />
            <View style={s.barRow}>
              <Txt style={s.barLabel}>Different weeks</Txt>
              <Txt style={s.barValue}>
                {c.gig_weeks_30d} / {next.weeks}
              </Txt>
            </View>
            <Bar value={c.gig_weeks_30d} max={next.weeks} color={C.amber} />
          </>
        ) : (
          <Txt style={s.formula}>Maximum booster reached.</Txt>
        )}
        <Txt style={s.note}>Gig income only raises your rate. Finexa never lends against it.</Txt>
      </Card>

      <HealthSection h={demo.health} />
    </Screen>
  );
}

const s = StyleSheet.create({
  step: { flexDirection: 'row', gap: 12 },
  stepNum: { width: 26, height: 26, borderRadius: 13, backgroundColor: C.indigo + '33', alignItems: 'center', justifyContent: 'center' },
  stepNumText: { color: '#A5B4FC', fontFamily: F.bold, fontSize: 13, lineHeight: 18 },
  stepHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 },
  stepTitle: { fontFamily: F.semibold, fontSize: 15 },
  stepResult: { fontFamily: F.bold, fontSize: 16, fontVariant: ['tabular-nums'] },
  formula: { color: C.muted, fontSize: 13, lineHeight: 19 },
  boosterLine: { fontFamily: F.semibold, fontSize: 16 },
  barRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: -6 },
  barLabel: { color: C.muted, fontSize: 13 },
  barValue: { fontFamily: F.medium, fontSize: 13, fontVariant: ['tabular-nums'] },
  note: { color: C.faint, fontSize: 12, lineHeight: 17 },
  tipCard: { gap: 6, borderColor: C.indigo + '66', backgroundColor: C.indigo + '1A' },
  tipGain: { color: C.green, fontFamily: F.bold, fontSize: 15, fontVariant: ['tabular-nums'] },
  tipText: { fontSize: 14, lineHeight: 20 },
});
