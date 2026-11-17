"""Regression checks for completed-bar confluence and prior-volume baseline."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from swing_confluence import evaluate


class SwingConfluenceTests(unittest.TestCase):
    def bars(self):
        dates = pd.bdate_range('2026-01-01', periods=65)
        bars = pd.DataFrame({
            'open': [100.] * 65, 'high': [110.] * 65, 'low': [90.] * 65,
            'close': [100.] * 65, 'volume': [100.] * 65,
            'MA20': [100.] * 65, 'K': [40.] * 65, 'D': [50.] * 65,
            'J': [20.] * 65, 'DIF': [-1.] * 65, 'DEA': [0.] * 65,
            'MACD': [-2.] * 65,
        }, index=dates)
        return bars

    def test_same_bar_cross_and_prior_volume(self):
        bars = self.bars()
        bars.loc[bars.index[-2], ['K', 'D']] = [60, 50]
        bars.loc[bars.index[-1], ['K', 'D', 'DIF', 'DEA', 'volume']] = [60, 50, 1, 0, 150]
        result = evaluate(bars, datetime(2026, 4, 15, 18, tzinfo=ZoneInfo('America/New_York')))
        self.assertEqual(result['signals'], [])  # KDJ crossed the day before MACD.
        bars.loc[bars.index[-2], ['K', 'D']] = [40, 50]
        result = evaluate(bars, datetime(2026, 4, 15, 18, tzinfo=ZoneInfo('America/New_York')))
        self.assertEqual(result['signals'][-1]['direction'], 'long')
        self.assertEqual(result['signals'][-1]['volume_ratio'], 1.5)
        self.assertTrue(result['signals'][-1]['volume_confirmed'])

    def test_partial_current_day_excluded(self):
        bars = self.bars()
        bars.loc[bars.index[-1], ['K', 'D', 'DIF', 'DEA']] = [60, 50, 1, 0]
        today = bars.index[-1].date()
        now = datetime(today.year, today.month, today.day, 12, tzinfo=ZoneInfo('America/New_York'))
        result = evaluate(bars, now)
        self.assertEqual(result['as_of'], bars.index[-2].date().isoformat())
        self.assertEqual(result['signals'], [])

    def test_death_cross_kept_with_weak_volume(self):
        bars = self.bars()
        bars[['K', 'D', 'DIF', 'DEA']] = [60, 50, 1, 0]
        bars.loc[bars.index[-1], ['K', 'D', 'DIF', 'DEA', 'volume']] = [40, 50, -1, 0, 50]
        result = evaluate(bars, datetime(2026, 4, 15, 18, tzinfo=ZoneInfo('America/New_York')))
        self.assertEqual(result['signals'][-1]['direction'], 'short')
        self.assertEqual(result['signals'][-1]['volume_ratio'], 0.5)
        self.assertFalse(result['signals'][-1]['volume_confirmed'])


if __name__ == '__main__':
    unittest.main()
