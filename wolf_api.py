"""Eight evidence-led research stages in the existing desktop application."""
from datetime import date,datetime,timezone
import json,sqlite3,threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import APIRouter,HTTPException
from fastapi.responses import Response
from pydantic import BaseModel,Field,ConfigDict,StrictInt
import v3_store as store
import sec_edgar
from wolf_finance import fetch_annual,valuation

router=APIRouter(prefix='/api/v3/wolf');LOCK=threading.RLock()
STAGES=[
 {'id':'overview','title':'公司全景','subtitle':'看清公司如何赚钱','questions':['商业模式与收入来源','竞争地位与行业趋势','关键风险及同行估值','看涨／中性／看跌的12–24个月情景']},
 {'id':'financials','title':'五年财务','subtitle':'现金流检验叙事','questions':['营收与利润增长是否连续','利润率与自由现金流是否改善','债务与资本回报率的口径','财务稳固还是出现衰退迹象']},
 {'id':'moat','title':'竞争护城河','subtitle':'判断优势能持续多久','questions':['品牌、网络效应、转换成本','成本优势与专有技术／专利','与主要对手逐项比较','五项1–10人工评分及事实依据']},
 {'id':'valuation','title':'估值与赔率','subtitle':'好公司也需要合理价格','questions':['P/E基准、同行及行业平均','FCFF现金流折现与假设','估值区间和敏感性','低估／合理／高估的失效条件']},
 {'id':'risks','title':'风险压力测试','subtitle':'先找可能输在哪里','questions':['经济、行业颠覆与竞争风险','监管与债务风险','按发生可能性与影响排序','风险触发、减轻办法与退出假设']},
 {'id':'growth','title':'长期增长','subtitle':'用边界约束远景','questions':['市场规模与行业增长率','扩张机会、新产品及AI优势','未来5–10年增长情景','产能、竞争与资本投入约束']},
 {'id':'institutional','title':'机构投资视角','subtitle':'写出买入与回避的理由','questions':['机构可能买入的证据链','机构可能回避的风险与流动性','长期投资论点与关键变量','13F等持仓资料滞后，不猜实时机构交易']},
 {'id':'debate','title':'多空交叉审查','subtitle':'让反方挑战你的结论','questions':['多方用数据提出论点','空方用数据提出反证','双方最强证据及未解决问题','平衡结论、观察事件与失效条件']},
]
MOAT=('brand','network','switching','cost','technology')
class Source(BaseModel):
 model_config=ConfigDict(extra='forbid')
 url:str=Field(default='',max_length=1500);published_on:str=Field(default='',max_length=10);claim:str=Field(default='',max_length=1500)
class Section(BaseModel):
 model_config=ConfigDict(extra='forbid')
 notes:str=Field(default='',max_length=12000);bull:str=Field(default='',max_length=6000);bear:str=Field(default='',max_length=6000);invalidation:str=Field(default='',max_length=3000)
 status:str='draft';sources:list[Source]=Field(default_factory=list,max_length=15);scores:dict[str,StrictInt|None]=Field(default_factory=dict)
class Threat(BaseModel):
 model_config=ConfigDict(extra='forbid')
 title:str=Field(min_length=1,max_length=200);impact:StrictInt=Field(ge=1,le=5);likelihood:StrictInt=Field(ge=1,le=5);mitigation:str=Field(default='',max_length=1000)
class Save(BaseModel):
 model_config=ConfigDict(extra='forbid')
 version:StrictInt=Field(ge=0);sections:dict[str,Section];risks:list[Threat]=Field(default_factory=list,max_length=20)
class Version(BaseModel):
 model_config=ConfigDict(extra='forbid')
 version:StrictInt=Field(ge=0)
class DCF(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True)
 version:StrictInt=Field(ge=0);fcff:float=Field(gt=0,le=1e9,allow_inf_nan=False);cash:float=Field(ge=0,le=1e9,allow_inf_nan=False);debt:float=Field(ge=0,le=1e9,allow_inf_nan=False);shares:float=Field(gt=0,le=1e9,allow_inf_nan=False)
 wacc:float=Field(gt=0,le=100,allow_inf_nan=False);terminal:float=Field(ge=-10,le=10,allow_inf_nan=False);years:StrictInt=5
 bear_growth:float=Field(ge=-80,le=100,allow_inf_nan=False);base_growth:float=Field(ge=-80,le=100,allow_inf_nan=False);bull_growth:float=Field(ge=-80,le=100,allow_inf_nan=False)
 market_price:float|None=Field(default=None,gt=0,le=1e9,allow_inf_nan=False);eps:float|None=Field(default=None,ge=-1e9,le=1e9,allow_inf_nan=False);peer_pe:float|None=Field(default=None,gt=0,le=1e6,allow_inf_nan=False);pe_basis:str=Field(default='',max_length=200)
 source_url:str=Field(min_length=1,max_length=1500);as_of:str=Field(min_length=10,max_length=10);basis_note:str=Field(min_length=1,max_length=2000)

def checked_source(url,day):
 p=urlparse(url)
 if p.scheme not in ('https','http') or not p.hostname or p.username:raise ValueError('来源请填写有效http/https原始链接')
 try:d=date.fromisoformat(day)
 except ValueError:raise ValueError('来源日期请用YYYY-MM-DD')
 if d>datetime.now(timezone.utc).date():raise ValueError('来源日期不能晚于今天')

def identity(s):
 try:s=store.symbol(s)
 except ValueError as e:raise HTTPException(400,str(e))
 item=store.instrument(s)
 if not item:raise HTTPException(404,'请先通过系统搜索选择标的')
 if item.get('asset_type') not in ('股票','ADR'):raise HTTPException(400,'华尔街之狼用于上市公司研究；ETF请研究其成分与发行人，不套用公司财报或DCF')
 return item

@contextmanager
def connection():
 path=store.DATA/'wallstreet-wolf.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(path,timeout=15);c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE IF NOT EXISTS cases(symbol TEXT PRIMARY KEY,version INTEGER NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY,symbol TEXT,version INTEGER,payload TEXT,created_at TEXT)')
 c.commit()
 try:
  with c:yield c
 finally:c.close()

def blank(item):
 return {'symbol':item['symbol'],'instrument':item,'version':0,'created_at':None,'updated_at':None,'workflow_version':'wolf-v1','sections':{s['id']:Section().model_dump() for s in STAGES},'risks':[],'finance':None,'valuation':None}

def read(s):
 item=identity(s)
 with LOCK,connection() as c:r=c.execute('SELECT payload FROM cases WHERE symbol=?',(item['symbol'],)).fetchone()
 return json.loads(r['payload']) if r else blank(item)

def write(s,version,mutate):
 item=identity(s)
 with LOCK,connection() as c:
  c.execute('BEGIN IMMEDIATE')
  row=c.execute('SELECT payload FROM cases WHERE symbol=?',(item['symbol'],)).fetchone()
  current=json.loads(row['payload']) if row else blank(item)
  if current['version']!=version:raise HTTPException(409,'研究已被另一窗口更新。请先导出本页草稿，再重新读取；不会覆盖新版本。')
  mutate(current);current['version']+=1;current['updated_at']=store.now();current['created_at']=current['created_at'] or current['updated_at']
  body=json.dumps(current,ensure_ascii=False,allow_nan=False)
  c.execute('INSERT OR REPLACE INTO cases VALUES(?,?,?,?)',(current['symbol'],current['version'],body,current['updated_at']))
  c.execute('INSERT INTO revisions(symbol,version,payload,created_at) VALUES(?,?,?,?)',(current['symbol'],current['version'],body,current['updated_at']))
  return current

def financial_observations(finance):
 rows=(finance or {}).get('rows',[]);bull=[];bear=[]
 if len(rows)>=2:
  a,b=rows[-2]['metrics'],rows[-1]['metrics']
  if b.get('revenue_growth') is not None:
   text=f"最近年度营收同比 {b['revenue_growth']:+.1f}%（截至{rows[-1]['end']}）";(bull if b['revenue_growth']>0 else bear).append(text)
  if b.get('free_cash_flow') is not None:
   text='最近年度自由现金流'+('为正' if b['free_cash_flow']>0 else '不为正')+'（经营现金流−Capex）';(bull if b['free_cash_flow']>0 else bear).append(text)
  if a.get('net_margin') is not None and b.get('net_margin') is not None:
   change=b['net_margin']-a['net_margin'];(bull if change>0 else bear).append(f'净利率同比变化 {change:+.1f}个百分点')
 return {'bull':bull,'bear':bear,'scope':'自动观察仅来自已取得的年度财报，不代表完整投资判断或机构持仓。'}

def decorate(case):
 result=dict(case);result['stages']=STAGES;result['completed']=sum(v['status']=='reviewed' for v in case['sections'].values());result['observations']=financial_observations(case.get('finance'))
 result['risks_ranked']=sorted([dict(r,priority=r['impact']*r['likelihood']) for r in case['risks']],key=lambda r:r['priority'],reverse=True)
 scores=case['sections']['moat'].get('scores',{});result['moat_score']=round(sum(scores.values())/5,1) if set(scores)==set(MOAT) and all(v is not None for v in scores.values()) else None
 result['scope']='八步证据研究；人工评分与情景假设单独标注，不连接券商，不伪造机构意见。'
 return result

@router.get('/{symbol}')
def get_case(symbol:str):return decorate(read(symbol))

@router.put('/{symbol}')
def save_case(symbol:str,body:Save):
 def mutate(case):
  sections=body.model_dump()['sections']
  if set(sections)!={s['id'] for s in STAGES}:raise ValueError('须保留全部八个研究步骤')
  for key,sec in sections.items():
   if sec['status'] not in ('draft','reviewed'):raise ValueError('步骤状态无效')
   if set(sec['scores'])-set(MOAT) or any(v is not None and not 1<=v<=10 for v in sec['scores'].values()):raise ValueError('护城河维度评分须在1–10之间')
   for source in sec['sources']:
    if source['url'] and source['published_on']:checked_source(source['url'],source['published_on'])
    elif sec['status']=='reviewed':raise ValueError('已核读来源须补齐原始链接和发布日期')
    if sec['status']=='reviewed' and not source['claim'].strip():raise ValueError('已核读来源须写明支持的事实')
   if sec['status']=='reviewed' and (not sec['notes'].strip() or not sec['sources'] or not sec['bull'].strip() or not sec['bear'].strip() or not sec['invalidation'].strip()):raise ValueError('标记已核读前，请补齐研究结论、来源、多空观点及失效条件')
   if key=='moat' and sec['status']=='reviewed' and (set(sec['scores'])!=set(MOAT) or any(v is None for v in sec['scores'].values())):raise ValueError('护城河已核读需要全部五项评分及依据')
  case['sections']=sections;case['risks']=body.model_dump()['risks']
 try:return decorate(write(symbol,body.version,mutate))
 except ValueError as e:raise HTTPException(400,str(e))

@router.post('/{symbol}/financials')
def load_financials(symbol:str,body:Version):
 case=read(symbol)
 if case['version']!=body.version:raise HTTPException(409,'版本已变更，请重新读取')
 try:finance=fetch_annual(case['symbol'])
 except (sec_edgar.EdgarUnavailable,ValueError) as e:raise HTTPException(503,'SEC年度财报尚未取得；保留原研究，不填造数值。'+str(e))
 return decorate(write(symbol,body.version,lambda c:c.update(finance=finance)))

@router.post('/{symbol}/valuation')
def calculate(symbol:str,body:DCF):
 p=body.model_dump(exclude={'version'})
 try:
  checked_source(p['source_url'],p['as_of'])
  if (p.get('eps') is not None or p.get('peer_pe') is not None) and not p['pe_basis'].strip():raise ValueError('P/E比较请标明EPS和同行的统计口径')
  result=valuation(p)
  return decorate(write(symbol,body.version,lambda c:c.update(valuation=result)))
 except ValueError as e:raise HTTPException(400,str(e))

def markdown(case):
 lines=[f"# 华尔街之狼｜{case['symbol']} · {case['instrument']['name']}",f"\n版本 {case['version']} · 更新 {case['updated_at'] or '尚未保存'} · 已人工核读 {case['completed']}/8",'\n研究草稿：自动财务事实、人工观点与估值假设分别标注。']
 f=case.get('finance')
 if f:
  lines+=['\n## SEC年度财务','\n| 年结 | 营收USD | 净利润USD | 自由现金流USD | 净利率% |','|---|---:|---:|---:|---:|']
  for row in f['rows']:
   m=row['metrics'];vals=[m.get(k) for k in ('revenue','net_income','free_cash_flow','net_margin')];lines.append('|'+row['end']+'|'+'|'.join('待核验' if v is None else f'{v:,.2f}' for v in vals)+'|')
  lines+=[f"\n来源：{f['source_url']}；抓取：{f['fetched_at']}。{f['notice']}"]
 for stage in STAGES:
  sec=case['sections'][stage['id']];lines+=['\n## '+stage['title']+' · '+('人工已核读' if sec['status']=='reviewed' else '待完善'),'核验问题：'+'；'.join(stage['questions']),sec['notes'] or '研究结论待填', '\n多方：'+(sec['bull'] or '待证据'), '\n空方：'+(sec['bear'] or '待证据'), '\n失效条件：'+(sec['invalidation'] or '待定义')]
  for source in sec['sources']:lines.append(f"\n来源（用户录入，需独立核验）：{source['url']} · {source['published_on']} · {source['claim']}")
  if stage['id']=='valuation' and case.get('valuation'):
   v=case['valuation'];lines+=['\nDCF情景：'+json.dumps(v['assumptions'],ensure_ascii=False)]
   lines += [f"\n{x['name']}：每股USD {x['per_share'] if x['per_share'] is not None else '不产生正股权价值'}；终值占比 {x['terminal_share_pct']:.1f}%" for x in v['cases']]
 if case['risks_ranked']:lines+=['\n## 风险优先级']+[f"- {r['title']}：{r['priority']}/25；{r['mitigation']}" for r in case['risks_ranked']]
 obs=case['observations'];lines+=['\n## 数据支持的交叉检查','\n多方财务观察：'+'；'.join(obs['bull'] or ['暂无自动证据']),'\n空方财务观察：'+'；'.join(obs['bear'] or ['暂无自动证据']),'\n平衡结论：核读进度不等于买卖信号。'+('八步已人工核读，仍需结合估值假设、价格结构与仓位计划。' if case['completed']==8 else '证据仍不完整，保留未解决问题，不生成确定买卖指令。')]
 return '\n'.join(lines)

@router.get('/{symbol}/report')
def report(symbol:str):return Response(markdown(decorate(read(symbol))),media_type='text/markdown; charset=utf-8')

@router.get('/{symbol}/history')
def history(symbol:str):
 item=identity(symbol)
 with connection() as c:rows=c.execute('SELECT version,created_at FROM revisions WHERE symbol=? ORDER BY version DESC LIMIT 50',(item['symbol'],)).fetchall()
 return {'items':[dict(r) for r in rows]}
