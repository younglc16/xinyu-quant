import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from indicators import add_indicators
from market_clock import calendar
from resonance_v1 import _scan, evaluate, evaluate_weekly


def sample():
    dates = calendar().sessions_in_range('2025-01-02', '2026-03-06')
    rng = np.random.default_rng(25)
    close = 100 * np.exp(np.cumsum(rng.normal(0, .022, len(dates))))
    return pd.DataFrame({
        'open': close, 'high': close * 1.024, 'low': close * .982,
        'close': close, 'volume': rng.integers(500, 1500, len(dates)),
    }, index=dates)


class ResonanceTests(unittest.TestCase):
    def test_rank_and_deduplication_use_suppressed_matches(self):
        b = add_indicators(sample()).iloc[:70]
        events = {key: pd.Series(False, index=b.index) for key in (
            'kdj_gold', 'kdj_dead', 'macd_gold', 'macd_dead',
            'decel_up', 'decel_dn', 'turn_up', 'turn_dn')}
        for key, indices in {
            'kdj_gold': [59, 60, 62, 65], 'macd_gold': [59],
            'turn_up': [59, 66, 69], 'decel_up': [60, 62, 65, 66, 69],
            'kdj_dead': [59, 61, 65], 'macd_dead': [59],
            'turn_dn': [69], 'decel_dn': [61, 65, 69],
        }.items():
            events[key].iloc[indices] = True
        with patch('resonance_v1._event_columns', return_value=events):
            signals, crosses, last = _scan(b, b.index[58])
            later, _, _ = _scan(b, b.index[61])
        self.assertEqual([(p['time'], p['rule_id']) for p in signals], [
            (str(b.index[i].date()), key)
            for i, key in [(59, 'R-L1'), (59, 'R-S1'), (65, 'R-L2'),
                           (65, 'R-S2'), (69, 'R-L3'), (69, 'R-S3')]])
        self.assertEqual(later, signals[2:])
        self.assertEqual(last['short']['rule_id'], 'R-S3')
        self.assertEqual(len([p for p in crosses if p['time'] == str(b.index[61].date())]), 1)

    def test_closed_only_staleness_and_truncated_samples(self):
        b = sample()
        cutoff = pd.Timestamp('2026-03-06T20:00Z')
        partial = evaluate(b, 'sample', 'split', cutoff)
        full = evaluate(b.iloc[:-1], 'sample', 'split', cutoff)
        self.assertEqual(partial['as_of'], '2026-03-05')
        self.assertEqual(partial['signals'], full['signals'])
        self.assertEqual(partial['crosses'], full['crosses'])
        self.assertFalse(evaluate(b.head(59), 'sample', 'split', cutoff)['available'])
        exactly60 = evaluate(b.head(60), 'sample', 'split', cutoff)
        self.assertTrue(exactly60['available'])
        self.assertFalse(exactly60['quality']['fresh'])
        self.assertEqual(exactly60['latest_signals'], [])
        self.assertFalse(evaluate(b.drop(b.index[63]), 'sample', 'split', cutoff)['available'])

    def test_zero_range_does_not_create_kdj_and_zero_volume_is_unknown(self):
        b = sample()
        b.loc[:, ['open', 'high', 'low', 'close']] = 80.0
        flat = evaluate(b, 'sample', 'split', pd.Timestamp('2026-03-07T00:00Z'))
        self.assertEqual((flat['signals'], flat['crosses']), ([], []))
        b = sample()
        b['volume'] = 0.
        zero = evaluate(b, 'sample', 'split', pd.Timestamp('2026-03-07T00:00Z'))
        self.assertTrue(zero['signals'])
        self.assertTrue(all(p['volume_confirmed'] is None for p in zero['signals']))


class WeeklyResonanceTests(unittest.TestCase):
    def test_holiday_week_aggregates_ohlcv_after_final_session(self):
        bars = sample()
        # Good Friday 2025. The final session is Thursday, April 17.
        before, _ = evaluate_weekly(bars, 'sample', 'split', '2025-04-17T20:14Z')
        after, outcome = evaluate_weekly(bars, 'sample', 'split', '2025-04-17T20:15Z')
        self.assertEqual(str(before.index[-1].date()), '2025-04-11')
        self.assertEqual(str(after.index[-1].date()), '2025-04-17')
        full_week = bars.loc['2025-04-14':'2025-04-17']
        self.assertEqual(len(full_week), 4)
        self.assertAlmostEqual(after.iloc[-1].high, full_week.high.max())
        self.assertAlmostEqual(after.iloc[-1].low, full_week.low.min())
        self.assertAlmostEqual(after.iloc[-1].open, full_week.open.iloc[0])
        self.assertAlmostEqual(after.iloc[-1].close, full_week.close.iloc[-1])
        self.assertAlmostEqual(after.iloc[-1].volume, full_week.volume.sum())
        self.assertTrue(outcome['quality']['fresh'])

    def test_week_uses_separate_indicators_and_incomplete_candles_are_excluded(self):
        bars = sample().loc[:'2026-03-06']
        before, state_before = evaluate_weekly(bars, 'sample', 'split', '2026-03-06T21:14Z')
        after, state_after = evaluate_weekly(bars, 'sample', 'split', '2026-03-06T21:15Z')
        self.assertEqual(str(before.index[-1].date()), '2026-02-27')
        self.assertEqual(str(after.index[-1].date()), '2026-03-06')
        self.assertTrue(state_after['available'])
        self.assertEqual(state_after['period'], 'weekly')
        self.assertTrue(state_before['quality']['fresh'])
        self.assertTrue(state_after['quality']['fresh'])
        self.assertTrue(all(p['time'] <= '2026-02-27' for p in state_before['signals']))
        unaggregated = add_indicators(bars)
        self.assertNotAlmostEqual(after.iloc[-1].DIF, unaggregated.iloc[-1].DIF)
        self.assertAlmostEqual(after.iloc[-1].VR3, after.volume.tail(3).mean() / after.volume.tail(20).mean())
        # A partial first week is discarded. An incomplete interior week is a data gap.
        self.assertNotIn(pd.Timestamp('2025-01-03'), after.index)
        missing, outcome = evaluate_weekly(bars.drop(pd.Timestamp('2025-05-20')), 'sample', 'split', '2026-03-06T21:15Z')
        self.assertNotIn(pd.Timestamp('2025-05-23'), missing.index)
        self.assertEqual(outcome['quality']['missing_weeks'], 1)
        self.assertFalse(outcome['available'])
