import copy,math,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wolf_finance import annual_series,valuation

class FinanceTests(unittest.TestCase):
 def facts(self):
  tags={}
  for tag in ('Revenues','NetIncomeLoss','NetCashProvidedByUsedInOperatingActivities','PaymentsToAcquirePropertyPlantAndEquipment','StockholdersEquity'):
   vals=[]
   for year in range(2019,2026):
    vals.append(dict(start=f'{year}-01-01',end=f'{year}-12-31',filed=f'{year+1}-02-10',form='10-K',val=1000*(year-2018),accn='000001-26-000001'))
   tags[tag]={'units':{'USD':vals}}
  return {'cik':1,'entityName':'Test company','facts':{'us-gaap':tags}}
 def test_five_year_selection_excludes_quarters_and_future(self):
  f=self.facts();f['facts']['us-gaap']['Revenues']['units']['USD'] += [dict(start='2025-10-01',end='2025-12-31',filed='2026-02-12',form='10-K',val=999999),dict(start='2026-01-01',end='2026-12-31',filed='2027-02-01',form='10-K',val=1)]
  out=annual_series(f,as_of='2026-10-26');self.assertEqual(len(out['rows']),5);self.assertEqual(out['rows'][-1]['end'],'2025-12-31');self.assertEqual(out['rows'][-1]['metrics']['revenue'],7000)
 def test_restatement_provenance_and_period_alignment(self):
  f=self.facts();f['facts']['us-gaap']['Revenues']['units']['USD'].append(dict(start='2025-01-01',end='2025-12-31',filed='2026-03-01',form='10-K/A',val=8000,accn='amended'))
  # A mismatched cash-flow start is not silently mixed into the revenue year.
  f['facts']['us-gaap']['NetCashProvidedByUsedInOperatingActivities']['units']['USD'][-1]['start']='2025-01-02'
  row=annual_series(f,as_of='2026-10-26')['rows'][-1];self.assertEqual(row['metrics']['revenue'],8000);self.assertEqual(row['provenance']['revenue']['accession'],'amended');self.assertIsNone(row['metrics']['free_cash_flow'])
 def test_missing_fiscal_year_not_called_complete(self):
  f=self.facts();v=f['facts']['us-gaap']['Revenues']['units']['USD'];f['facts']['us-gaap']['Revenues']['units']['USD']=[x for x in v if x['end']!='2023-12-31']
  out=annual_series(f,as_of='2026-10-26');self.assertEqual(len(out['rows']),5);self.assertFalse(out['complete_five_years']);self.assertTrue(out['issues'])
 def test_productive_assets_capex_fallback_is_traceable(self):
  f=self.facts();gaap=f['facts']['us-gaap'];gaap['PaymentsToAcquireProductiveAssets']=gaap.pop('PaymentsToAcquirePropertyPlantAndEquipment')
  r=annual_series(f,as_of='2026-10-26')['rows'][-1];self.assertEqual(r['metrics']['free_cash_flow'],0);self.assertEqual(r['provenance']['capex']['tag'],'PaymentsToAcquireProductiveAssets')
 def test_missing_and_negative_equity_not_fabricated(self):
  f=self.facts();f['facts']['us-gaap']['StockholdersEquity']['units']['USD'][-1]['val']=-100
  out=annual_series(f,as_of='2026-10-26');self.assertIsNone(out['rows'][-1]['metrics']['roe']);self.assertIsNone(out['rows'][-1]['metrics']['long_term_debt'])
 def params(self):return dict(fcff=100,cash=20,debt=10,shares=10,wacc=10,terminal=2,years=5,bear_growth=0,base_growth=0,bull_growth=0)
 def test_dcf_known_constant_cashflow_and_invalid_assumptions(self):
  p=self.params();v=valuation(p);expected=sum(100/1.1**i for i in range(1,6))+100*1.02/(.1-.02)/1.1**5+10
  self.assertAlmostEqual(v['cases'][1]['per_share'],expected/10)
  for change in [dict(wacc=2),dict(shares=0),dict(fcff=float('nan')),dict(years=True),dict(bear_growth=20,base_growth=10)]:
   with self.assertRaises(ValueError):valuation(dict(p,**change))

class WorkflowTests(unittest.TestCase):
 def setUp(self):
  from fastapi.testclient import TestClient
  import v3_store as store
  from api_server import app
  self.store=store;self.tmp=tempfile.TemporaryDirectory();p=Path(self.tmp.name);self.patches=[patch.object(store,'DATA',p),patch.object(store,'DB',p/'main.sqlite3')]
  for x in self.patches:x.start()
  store.init();self.client=TestClient(app)
 def tearDown(self):
  self.client.close()
  for x in reversed(self.patches):x.stop()
  self.tmp.cleanup()
 def payload(self):
  d=self.client.get('/api/v3/wolf/NVDA').json();return dict(version=d['version'],sections=d['sections'],risks=[])
 def test_save_eight_stages_and_revision_conflict(self):
  p=self.payload();p['sections']['overview']['notes']='真实研究待核实';r=self.client.put('/api/v3/wolf/NVDA',json=p);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['version'],1)
  self.assertEqual(self.client.put('/api/v3/wolf/NVDA',json=p).status_code,409)
  self.assertEqual(len(self.client.get('/api/v3/wolf/NVDA/history').json()['items']),1)
 def test_review_requires_sources_both_sides_invalidation_and_moat_scores(self):
  p=self.payload();p['sections']['moat']['status']='reviewed';self.assertEqual(self.client.put('/api/v3/wolf/NVDA',json=p).status_code,400)
  s=p['sections']['moat'];s.update(notes='测试',bull='数据支持',bear='反证',invalidation='待验证',sources=[dict(url='https://www.sec.gov/test',published_on='2026-01-01',claim='测试')],scores=dict(brand=7,network=7,switching=7,cost=7,technology=7))
  r=self.client.put('/api/v3/wolf/NVDA',json=p);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['moat_score'],7)
 def test_source_scheme_missing_stage_and_etf_rejected(self):
  p=self.payload();p['sections']['overview']['sources']=[dict(url='javascript:alert(1)',published_on='2026-01-01',claim='x')]
  self.assertEqual(self.client.put('/api/v3/wolf/NVDA',json=p).status_code,400)
  p=self.payload();p['sections'].pop('debate');self.assertEqual(self.client.put('/api/v3/wolf/NVDA',json=p).status_code,400)
  self.assertEqual(self.client.get('/api/v3/wolf/QQQ').status_code,400)
 def test_financial_failure_keeps_existing_case(self):
  with patch('wolf_api.fetch_annual',side_effect=RuntimeError('test')):
   # Use provider's public failure type.
   import sec_edgar
   with patch('wolf_api.fetch_annual',side_effect=sec_edgar.EdgarUnavailable('unavailable')):
    r=self.client.post('/api/v3/wolf/NVDA/financials',json={'version':0});self.assertEqual(r.status_code,503)
  self.assertEqual(self.client.get('/api/v3/wolf/NVDA').json()['version'],0)
 def test_financial_persistence_and_report(self):
  finance=annual_series(FinanceTests().facts(),as_of='2026-10-26');finance.update(source_url='https://data.sec.gov/test',fetched_at='2026-10-26T00:00:00Z')
  with patch('wolf_api.fetch_annual',return_value=finance):r=self.client.post('/api/v3/wolf/NVDA/financials',json={'version':0})
  self.assertEqual(r.status_code,200,r.text)
  text=self.client.get('/api/v3/wolf/NVDA/report').text;self.assertIn('五年财务',text);self.assertIn('2025-12-31',text);self.assertIn('待完善',text)
 def test_valuation_and_cross_origin_guard(self):
  p=dict(FinanceTests().params(),version=0,source_url='https://www.sec.gov/test',as_of='2026-01-01',basis_note='人工测试FCFF假设')
  r=self.client.post('/api/v3/wolf/NVDA/valuation',json=p);self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(self.client.post('/api/v3/wolf/NVDA/valuation',json=p,headers={'Origin':'https://other.example'}).status_code,403)
  self.assertEqual(self.client.get('/api/v3/wolf/NVDA').json()['valuation']['cases'][0]['name'],'悲观')
 def test_risk_ranking_and_original_watchlist_unchanged(self):
  before=self.store.watchlist();p=self.payload();p['risks']=[dict(title='低',impact=1,likelihood=1,mitigation='观察'),dict(title='高',impact=5,likelihood=4,mitigation='复核')]
  out=self.client.put('/api/v3/wolf/NVDA',json=p).json();self.assertEqual(out['risks_ranked'][0]['title'],'高');self.assertEqual(self.store.watchlist(),before)

if __name__=='__main__':unittest.main()
