import sys, tempfile, json, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import v3_store as store
import v3_api as api
import data_provider as dp
import pandas as pd

class Integration(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.patches=[patch.object(store,'ROOT',self.root),patch.object(store,'DATA',self.root/'data'),patch.object(store,'DB',self.root/'data'/'test.sqlite3')]
  for p in self.patches:p.start()
  (self.root/'watchlist.json').write_text(json.dumps({'groups':{'自定义组':['ZZZZ','NVDA'],'空分组':[]}}))
  store.init();api.research_store.init()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def test_migration_and_restart(self):
  tags={t['name']:t for t in store.tags()};self.assertIn('空分组',tags)
  self.assertFalse(store.instrument('ZZZZ')['verified'])
  store.remove_watch('NVDA',1);store.init();self.assertNotIn('NVDA',[w['symbol'] for w in store.watchlist()])
  self.assertIn('ZZZZ',[w['symbol'] for w in store.watchlist()])
 def test_conflict_and_tag_delete(self):
  tid=store.add_tag('我的主题')['id'];w=store.save_watch('COIN','long','保留', [tid]);self.assertEqual(w['version'],1)
  with self.assertRaises(RuntimeError):store.save_watch('COIN','short','错误',[],None)
  store.delete_tag(tid)
  with self.assertRaises(RuntimeError):store.remove_watch('COIN',1)
  w=next(w for w in store.watchlist() if w['symbol']=='COIN');self.assertEqual(w['note'],'保留');self.assertEqual(w['tags'],[])
  base=next(t for t in store.tags() if t['name']=='Web3');store.delete_tag(base['id']);store.init();self.assertNotIn('Web3',[t['name'] for t in store.tags()])
 def test_verified_resolve(self):
  store.register(dict(symbol='ZZZZ',name='Resolved',exchange='NYSE',asset_type='股票'))
  self.assertTrue(store.instrument('ZZZZ')['verified'])
 def test_plan_archive_preserves_cost_and_review(self):
  pid=store.create_plan(dict(symbol='NVDA',mode='swing',direction='long',cost=100,quantity=10,stop_pct=15,notes='原计划'))
  store.close_plan(pid,1,'结束复盘');p=store.list_plans()[0];self.assertEqual(p['cost'],100);self.assertEqual(p['status'],'closed');self.assertIn('原计划',p['notes']);self.assertIn('结束复盘',p['notes'])
  with self.assertRaises(RuntimeError):store.close_plan(pid,2)
 def test_formation_http_and_legacy_price_only(self):
  from fastapi.testclient import TestClient
  from api_server import app
  from band_strategy import band_exit_plan, band_add_3570
  from indicators import sell_plan_3221
  with TestClient(app) as client:
   root='/api/v3/formations'
   book=client.get(root).json()
   self.assertEqual(book['hard_stop_pct'],20)
   self.assertEqual([r['cap_pct'] for r in book['entry']],[17,25,3])
   payload={'price':125,'cost':100,'shares':70,'exit_count':1,'exit_base_shares':100}
   result=client.post(root+'/evaluate',json=payload).json()
   self.assertEqual(result['suggested_reduce_shares'],20)
   self.assertEqual(result['rule_version'],book['version'])
   self.assertEqual(client.post(root+'/evaluate',json={**payload,'exit_base_shares':60}).status_code,400)
   self.assertFalse(result['order_enabled'])
   self.assertFalse(store.list_plans())
  self.assertEqual(band_exit_plan(100,165)['sl_hard'],80)
  self.assertEqual(band_exit_plan(100,165)['done'],[])
  self.assertEqual(sell_plan_3221(100,165)['done'],[])
  self.assertFalse(band_add_3570(100,165)['confirm'])
 def test_only_new_long_swing_plans_apply_formation_stop_ceiling(self):
  from fastapi.testclient import TestClient
  from api_server import app
  long={'symbol':'NVDA','mode':'swing','direction':'long','cost':100,'quantity':10,'stop_pct':25}
  store.create_plan(long)
  with TestClient(app) as client:
   self.assertEqual(client.post('/api/v3/plans',json=long).status_code,400)
   self.assertEqual(client.get('/api/v3/plans').json()['items'][0]['stop_pct'],25)
   self.assertEqual(client.post('/api/v3/plans',json={**long,'stop_pct':20}).status_code,200)
   self.assertEqual(client.post('/api/v3/plans',json={**long,'direction':'short'}).status_code,200)
 def test_snapshot_nulls_and_roundtrip(self):
  store.put_snapshot('x',api.clean({'a':float('nan'),'b':3}));self.assertEqual(store.snapshot('x'),{'a':None,'b':3})
 def test_reference_excludes_last_and_chart_alignment(self):
  ix=pd.date_range('2026-01-01',periods=80,freq='B');close=pd.Series(range(100,180),index=ix,dtype=float)
  frame=pd.DataFrame({'open':close-1,'high':close+2,'low':close-2,'close':close,'volume':1000.0},index=ix);frame.iloc[-1,frame.columns.get_loc('low')]=1
  with patch.object(dp,'get_daily',return_value=frame),patch.object(dp,'get_index_daily',return_value=frame),patch.object(dp,'source_label',return_value='TEST ONLY'):
   d=api.build_analysis('NVDA','daily','QQQ');self.assertEqual(d['metrics']['low5'],172);self.assertEqual(len(d['chart']),80)
   for key in ['k','d','j','dif','dea','macd']:self.assertIsInstance(d['chart'][-1][key],float)
   with patch.object(dp,'get_intraday',return_value=None):
    with self.assertRaises(ValueError):api.build_analysis('NVDA','intraday','QQQ')
 def test_legacy_chart_snapshot_uses_its_own_dataset(self):
  from test_resonance_v1 import sample
  raw=sample()
  earlier=api.research_store.save_dataset('NVDA',raw,'historic fixture','qfq')
  newer=api.research_store.save_dataset('NVDA',raw*1.2,'newer fixture','qfq')
  self.assertNotEqual(earlier,newer)
  cache={'period':'daily','decision':{'dataset_id':earlier}}
  api.restore_chart_resonance(cache,'NVDA')
  self.assertEqual(cache['resonance']['source'],'historic fixture')
  self.assertTrue(cache['resonance']['signals'])
  self.assertEqual(cache['resonance']['latest_signals'],[])
  mismatch={'period':'daily','decision':{'dataset_id':earlier}}
  api.restore_chart_resonance(mismatch,'MU')
  self.assertNotIn('resonance',mismatch)
 def test_weekly_snapshot_matches_the_analysis_chart(self):
  from test_resonance_v1 import sample
  raw=sample()
  with patch.object(dp,'get_daily',return_value=raw),patch.object(dp,'get_index_daily',return_value=raw),patch.object(dp,'source_label',return_value='test provider'):
   daily=api.build_analysis('NVDA','daily','QQQ')
   weekly=api.build_analysis('NVDA','weekly','QQQ')
  from_daily=api.weekly_snapshot(daily,'NVDA')
  self.assertEqual(from_daily['chart'],weekly['chart'])
  signals=weekly['resonance']['signals']
  self.assertEqual(from_daily['resonance']['signals'],signals)
  self.assertTrue(weekly['resonance']['available'])
  self.assertNotEqual(daily['chart'][-1]['dif'],weekly['chart'][-1]['dif'])
  candles={r['time'][:10] for r in weekly['chart']}
  self.assertTrue(all(p['time'] in candles for p in signals+weekly['resonance']['crosses']))
  store.put_snapshot('NVDA:weekly:QQQ',{**weekly,'daily_as_of':'2025-12-01'})
  with patch.object(api,'JOBS',{}),patch.object(api.POOL,'submit'):
   first=api.analysis('NVDA',period='weekly')['data']
  self.assertEqual(first['daily_as_of'],daily['daily_as_of'])
  self.assertEqual(first['chart'],weekly['chart'])
 def test_share_class_normalization(self):
  self.assertEqual(dp._norm_symbol('BRK.B'),'BRK.B');self.assertEqual(dp._norm_symbol('nvda.us'),'NVDA')
if __name__=='__main__':unittest.main(verbosity=2)
