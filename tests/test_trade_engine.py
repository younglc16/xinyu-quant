import os,sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import trade_engine as e
from market_clock import clock,calendar
import v3_store as store
import research_store as rs
import alpaca_data

def bars(n=260):
    dates=calendar().sessions_in_range('2025-01-02','2026-10-16')[:n]
    close=100+np.arange(n)*.3+np.sin(np.arange(n)/8)*3
    return pd.DataFrame({'open':close-.1,'high':close+1,'low':close-1,'close':close,'volume':1000000.},index=dates)

class EngineTests(unittest.TestCase):
    def test_holiday_early_close_and_weekend(self):
        self.assertEqual(clock('2026-11-27T18:14:00Z')['expected_session'],'2026-11-25')
        self.assertEqual(clock('2026-11-27T18:16:00Z')['expected_session'],'2026-11-27')
        self.assertEqual(clock('2026-10-18T12:00:00Z')['expected_session'],'2026-10-16')
    def test_excludes_future_and_incomplete(self):
        d=bars();now=str(d.index[-2].date())+'T22:00:00Z'
        clean,q=e.prepare(d,now);self.assertEqual(clean.index[-1],d.index[-2]);self.assertTrue(q['fresh']);self.assertEqual(q['incomplete_rows'],1)
    def test_missing_invalid_duplicate_and_stale_disable_current(self):
        d=bars();now=str(d.index[-1].date())+'T22:00:00Z'
        for bad in [d.drop(d.index[40]),pd.concat([d,d.tail(1)])]:
            out=e.decision(bad,'test',now=now);self.assertFalse(out['current_eligible']);self.assertIsNone(out['sides']['long']['sizing'])
        bad=d.copy();bad.loc[bad.index[40],'high']=1
        self.assertFalse(e.decision(bad,'test',now=now)['current_eligible'])
        self.assertFalse(e.decision(d,'test',now='2026-10-18T12:00:00Z')['current_eligible'])
    def test_features_causal_and_prior_threshold(self):
        d=bars();a=e.features(d);changed=d.copy();changed.iloc[180:,:4]*=10;b=e.features(changed)
        pd.testing.assert_frame_equal(a.iloc[:180],b.iloc[:180]);self.assertEqual(a.high55.iloc[80],d.high.iloc[25:80].max())
    def test_risk_caps_include_costs(self):
        p=e.parameters();s=e.size(100,2,p)
        self.assertLessEqual(s['planned_loss'],s['risk_budget']);self.assertLessEqual(s['notional'],10000)
        self.assertEqual(s['shares'],100)
        self.assertEqual(e.size(1e6,100,p)['shares'],0)
    def make_fills(self,sign):
        dates=pd.to_datetime(['2026-10-08','2026-10-09','2026-10-12','2026-10-13'])
        f=pd.DataFrame({'open':[100,100,85 if sign==1 else 115,100],'high':[101,101,116,101],'low':[99,99,84,99],'close':[100,100,100,100], 'atr':2.,'low20':50.,'high20':150.,'signal':[sign,0,0,0]},index=dates)
        return f
    def test_next_open_and_gap_stop(self):
        p=e.parameters({'fee_bps':0,'slippage_bps':0});out=e.simulate(self.make_fills(1),p,1);t=out['trades'][0]
        self.assertEqual(t['entry_date'],'2026-10-09');self.assertEqual(t['signal_date'],'2026-10-08');self.assertEqual(t['exit'],85);self.assertEqual(t['net_pnl'],-1500)
    def test_short_gap_and_weekend_borrow(self):
        p=e.parameters({'fee_bps':0,'slippage_bps':0,'borrow_pct':36.5});out=e.simulate(self.make_fills(-1),p,1);t=out['trades'][0]
        self.assertEqual(t['exit'],115);self.assertAlmostEqual(t['borrow_cost'],30);self.assertEqual(t['net_pnl'],-1530)
    def test_stop_active_on_entry_day_and_costs_monotonic(self):
        f=self.make_fills(1);f.loc[f.index[1],'low']=90
        a=e.simulate(f,e.parameters({'fee_bps':0,'slippage_bps':0}),1);b=e.simulate(f,e.parameters(),1)
        self.assertEqual(a['trades'][0]['entry_date'],a['trades'][0]['exit_date']);self.assertLess(b['metrics']['end_equity'],a['metrics']['end_equity'])
    def test_backtest_saved_json_and_holdout_reset(self):
        d=bars();out=e.backtest(d,'test',now=str(d.index[-1].date())+'T22:00:00Z');json.dumps(out,allow_nan=False)
        self.assertEqual(out['holdout']['from'],str(d.index[int(len(d)*.7)].date()));self.assertEqual(out['parameters']['equity'],100000)
        self.assertGreater(len(out['full']['curve']),len(out['holdout']['curve']))
    def test_append_only_datasets_and_records(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'DATA',Path(tmp)),patch.object(store,'DB',Path(tmp)/'db.sqlite3'):
            store.init();rs.init();d=bars();ident=rs.save_dataset('NVDA',d,'test','split');self.assertEqual(ident,rs.save_dataset('NVDA',d,'test','split'))
            new=d.copy();new.iloc[-1,3]+=.2;other=rs.save_dataset('NVDA',new,'test','split');self.assertNotEqual(ident,other)
            record=rs.record('setup','NVDA',ident,{'version':'v1','price':123});self.assertEqual(rs.detail(record)['dataset_id'],ident);self.assertEqual(rs.dataset('NVDA')[1]['id'],other)
    def test_alpaca_pagination_and_no_feed_downgrade(self):
        bar={'t':'2026-10-15T04:00:00Z','o':100,'h':102,'l':99,'c':101,'v':1e6}
        client=Mock();a=Mock(status_code=200);a.json.return_value={'bars':{'NVDA':[bar]},'next_page_token':'next'};b=Mock(status_code=200);b.json.return_value={'bars':{'NVDA':[{**bar,'t':'2026-10-16T04:00:00Z'}]},'next_page_token':None};client.get.side_effect=[a,b]
        with patch.dict(os.environ,{'APCA_API_KEY_ID':'test','APCA_API_SECRET_KEY':'test'}):
            d=alpaca_data.daily('NVDA',100,client);self.assertEqual(len(d),2);self.assertEqual(client.get.call_args.kwargs['params']['feed'],'sip');self.assertEqual(client.get.call_args.kwargs['params']['adjustment'],'split')
            client.get.side_effect=None;client.get.return_value=Mock(status_code=403)
            with self.assertRaises(ValueError):alpaca_data.daily('NVDA',100,client)

if __name__=='__main__':unittest.main(verbosity=2)
