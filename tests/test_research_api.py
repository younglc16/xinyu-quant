import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api_server import app
import v3_store as store
import research_store as records
from market_clock import calendar,clock
from test_trade_engine import bars

class ResearchAPI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();p=Path(self.tmp.name)
        self.patches=[patch.object(store,'DATA',p),patch.object(store,'DB',p/'db.sqlite3')]
        for x in self.patches:x.start()
        store.init();records.init();d=bars();d.index=calendar().sessions_in_range('2024-01-02',clock()['expected_session'])[-len(d):]
        records.save_dataset('NVDA',d,'synthetic test','split');self.client=TestClient(app)
    def tearDown(self):
        self.client.close()
        for x in reversed(self.patches):x.stop()
        self.tmp.cleanup()
    def test_create_history_and_read_before_static_catchall(self):
        created=self.client.post('/api/v3/research/setups/NVDA',json={});self.assertEqual(created.status_code,200,created.text)
        record=created.json()['id'];history=self.client.get('/api/v3/research/records?symbol=NVDA');self.assertEqual(history.status_code,200);self.assertEqual(history.json()['items'][0]['id'],record)
        read=self.client.get('/api/v3/research/records/'+record);self.assertEqual(read.status_code,200);self.assertEqual(read.json()['payload']['as_of'],clock()['expected_session'])
    def test_stale_dataset_cannot_save_current_sizing(self):
        d,meta=records.dataset('NVDA');records.save_dataset('NVDA',d.iloc[:-2],meta['source'],'split')
        self.assertEqual(self.client.post('/api/v3/research/setups/NVDA',json={}).status_code,409)
        body=self.client.post('/api/v3/research/decision/NVDA',json={}).json();self.assertFalse(body['current_eligible']);self.assertIsNone(body['sides']['short']['sizing'])
    def test_validation_and_local_write_guard(self):
        self.assertEqual(self.client.post('/api/v3/research/backtests/NVDA',json={'risk_pct':99}).status_code,422)
        self.assertEqual(self.client.post('/api/v3/research/setups/NVDA',json={},headers={'Origin':'https://unrelated.example'}).status_code,403)
    def test_watch_quotes_missing_rows_are_not_fabricated(self):
        response=self.client.get('/api/v3/watch-quotes');self.assertEqual(response.status_code,200);self.assertEqual(response.json()['items'],[])
        store.put_snapshot('NVDA:daily:QQQ',{'daily_as_of':'2000-01-03','daily_source':'historical test','metrics':{'price':100,'change_pct':2}})
        response=self.client.get('/api/v3/watch-quotes');items=response.json()['items'];self.assertEqual(len(items),1);self.assertEqual(items[0]['symbol'],'NVDA');self.assertFalse(items[0]['fresh']);self.assertEqual(items[0]['source'],'historical test')

    def test_swing_record_retains_separate_version_and_data(self):
        response=self.client.post('/api/v3/research/swing-setups/NVDA',json={})
        self.assertEqual(response.status_code,200,response.text)
        payload=response.json();record=records.detail(payload['id'])
        self.assertEqual(record['kind'],'swing-setup');self.assertEqual(record['rule_version'],'swing-confluence-plan-v1')
        self.assertEqual(record['dataset_id'],payload['data']['dataset_id'])
        self.assertFalse(payload['data']['sides']['short']['executable'])
        self.assertNotIn('full',payload['data'])

    def test_swing_stale_save_is_blocked_and_bad_params_rejected(self):
        raw,meta=records.dataset('NVDA');records.save_dataset('NVDA',raw.iloc[:-2],meta['source'],'split')
        self.assertEqual(self.client.post('/api/v3/research/swing-setups/NVDA',json={}).status_code,409)
        self.assertEqual(self.client.post('/api/v3/research/swing-decision/NVDA',json={'risk_pct':99}).status_code,422)

    def test_plan_risk_is_research_only(self):
        store.create_plan({'symbol':'NVDA','mode':'swing','direction':'short','cost':100,'quantity':10,'stop_pct':10,'notes':''})
        d=self.client.get('/api/v3/research/plan-risk').json();self.assertEqual(d['short_notional'],1000);self.assertEqual(d['planned_stop_loss'],100);self.assertIn('不是实盘',d['scope'])

if __name__=='__main__':unittest.main()
