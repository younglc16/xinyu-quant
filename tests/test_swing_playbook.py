import unittest,json
from unittest.mock import patch
import pandas as pd
from test_trade_engine import bars
import swing_playbook as swing
import market_pulse

class SwingPlaybook(unittest.TestCase):
    def setUp(self):
        self.raw=bars();self.now=str(self.raw.index[-1].date())+'T22:00:00Z'
    def fixture(self,side='long',ratio=1.2,cross=True):
        close=float(self.raw.close.iloc[-1]);up=side=='long'
        return {'available':True,'stale':False,'latest_signal':{'direction':side} if cross else None,
                'latest':{'kdj_side':'up' if up else 'down','macd_side':'up' if up else 'down',
                          'ma20':close-1 if up else close+1,'volume_ratio':ratio}}
    def run_with(self,value,raw=None,now=None):
        with patch.object(swing.swing_confluence,'evaluate',return_value=value):
            return swing.decision(self.raw if raw is None else raw,'synthetic test',now=now or self.now)
    def test_long_trigger_is_never_executable(self):
        d=self.run_with(self.fixture());x=d['sides']['long']
        self.assertTrue(x['triggered']);self.assertFalse(x['executable']);self.assertFalse(d['sides']['short']['triggered'])
        self.assertLess(x['stop'],x['entry']);self.assertGreater(x['target2r'],x['entry']);self.assertNotIn('channel_exit',x)
        self.assertIn('尚未验证',d['validation']);json.dumps(d,allow_nan=False)
    def test_short_direction_and_targets(self):
        d=self.run_with(self.fixture('short'));x=d['sides']['short'];self.assertTrue(x['triggered'])
        self.assertGreater(x['stop'],x['entry']);self.assertLess(x['target2r'],x['entry']);self.assertFalse(x['executable'])
        self.assertIn('借券',str(x['execution_checks']))
    def test_no_cross_or_low_volume_never_trigger(self):
        for f in [self.fixture(cross=False),self.fixture(ratio=.99),self.fixture(ratio=None)]:
            self.assertFalse(self.run_with(f)['sides']['long']['triggered'])
    def test_trend_conflict_prevents_trigger(self):
        f=self.fixture();f['latest']['ma20']=float(self.raw.close.iloc[-1])+1
        self.assertFalse(self.run_with(f)['sides']['long']['triggered'])
    def test_invalid_missing_and_stale_disable_sizing(self):
        bad=self.raw.copy();bad.loc[bad.index[40],'high']=1
        for raw,now in [(bad,self.now),(self.raw.drop(self.raw.index[40]),self.now),(self.raw,'2026-10-18T12:00:00Z')]:
            d=self.run_with(self.fixture(),raw,now)
            for x in d['sides'].values():self.assertFalse(x['triggered']);self.assertIsNone(x['sizing'])
    def test_risk_budget_is_respected_and_parameters_saved(self):
        d=self.run_with(self.fixture());x=d['sides']['long']['sizing'];self.assertLessEqual(x['planned_loss'],x['risk_budget']);self.assertLessEqual(x['notional'],10000)
    def test_incomplete_and_future_candles_do_not_change_plan(self):
        expected=swing.decision(self.raw,'test',now=self.now)
        future=self.raw.copy();extra=self.raw.tail(1).copy();extra.index=[self.raw.index[-1]+pd.Timedelta(days=7)];extra.iloc[:,:4]*=10
        actual=swing.decision(pd.concat([future,extra]),'test',now=self.now)
        self.assertEqual(expected['sides'],actual['sides']);self.assertEqual(expected['as_of'],actual['as_of'])
    def test_qqq_history_is_real_completed_close(self):
        with patch.object(market_pulse.dp,'get_index_daily',return_value=self.raw),patch.object(market_pulse.dp,'source_label',return_value='synthetic test'):
            d=market_pulse._qqq(self.raw.index[-1].date(),pd.Timestamp(self.now).to_pydatetime())
        self.assertEqual(len(d['history']),30);self.assertEqual(d['history'][-1]['value'],round(float(self.raw.close.iloc[-1]),2));self.assertEqual(d['history'][-1]['date'],d['as_of'])

if __name__=='__main__':unittest.main()
