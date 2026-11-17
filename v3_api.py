"""Unified desktop API: persistence, background market loading, and auditable references."""
from __future__ import annotations
import json, math, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, ConfigDict
import data_provider as dp
import demo_market
import sec_edgar
import gold_signal
import formation_rules
import market_pulse
import swing_confluence
import resonance_v1
import swing_playbook
import trade_engine
import research_store
from market_clock import freshness, weekly_freshness
from indicators import add_indicators
import v3_store as store

router=APIRouter(prefix='/api/v3')
store.init()
research_store.init()
POOL=ThreadPoolExecutor(max_workers=3,thread_name_prefix='xinyu-market')
LOCK=threading.Lock()
JOBS={}
NY=ZoneInfo('America/New_York')

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Watch(Model):
    symbol:str=Field(min_length=1,max_length=16)
    direction:Literal['long','short','watch']='watch'
    note:str=Field(default='',max_length=1500)
    tag_ids:list[int]=Field(default_factory=list,max_length=40)
    version:int|None=Field(default=None,ge=1)
class Tag(Model): name:str=Field(min_length=1,max_length=40)
class Plan(Model):
    symbol:str=Field(min_length=1,max_length=16)
    mode:Literal['swing','intraday']
    direction:Literal['long','short']='long'
    cost:float=Field(gt=0,le=1e9,allow_inf_nan=False)
    quantity:int=Field(gt=0,le=100000000)
    stop_pct:float=Field(gt=0,lt=100,allow_inf_nan=False)
    started_on:date|None=None
    notes:str=Field(default='',max_length=3000)
class Version(Model):
    version:int=Field(ge=1)
    review:str=Field(default='',max_length=3000)

def invoke(fn,*args,**kwargs):
    try: return fn(*args,**kwargs)
    except RuntimeError as e: raise HTTPException(409,str(e))
    except ValueError as e: raise HTTPException(400,str(e))

def clean(v):
    if isinstance(v,dict): return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)): return [clean(x) for x in v]
    if isinstance(v,(pd.Timestamp,datetime)): return v.isoformat()
    if isinstance(v,(np.bool_,)): return bool(v)
    if isinstance(v,(np.integer,)): return int(v)
    if isinstance(v,(float,np.floating)): return float(v) if math.isfinite(v) else None
    return v

@router.get('/bootstrap')
def bootstrap(): return {'version':'3.3.0','demo':demo_market.enabled(),'watchlist':store.watchlist(),'tags':store.tags(),'indices':[{'symbol':s,'name':n+' ETF代理'} for s,n in dp.INDEX_CHOICES.items()]}

@router.get('/watch-quotes')
def watch_quotes():
    """Read dated snapshots for watchlist rows. Never start N provider requests."""
    items=[]
    for instrument in store.watchlist():
        symbol=instrument['symbol']
        with store.connection() as c:
            row=c.execute('SELECT payload FROM snapshots WHERE key LIKE ? ORDER BY fetched_at DESC LIMIT 1',(symbol+':daily:%',)).fetchone()
        if not row: continue
        data=json.loads(row['payload']);metrics=data.get('metrics') or {}
        as_of=data.get('daily_as_of') or data.get('as_of')
        dated=freshness(as_of)
        items.append({'symbol':symbol,'price':metrics.get('price'),'change_pct':metrics.get('change_pct'),'as_of':as_of,'fresh':dated['fresh'],'source':data.get('daily_source') or data.get('source') or '来源待核验'})
    return clean({'items':items,'scope':'本机日线快照；缺失证券不填假价格','fetched_at':store.now()})

@router.get('/search')
def search(q:str=Query(default='',max_length=80),remote:bool=False):
    local=store.search(q)
    if demo_market.enabled() or not remote or len(q.strip())<1: return {'items':local,'source':'local','message':'本地证券目录；可点“联网补充”搜索其他美股'}
    try:
        r=requests.get('https://query1.finance.yahoo.com/v1/finance/search',params={'q':q.strip(),'quotesCount':12,'newsCount':0},headers={'User-Agent':'Mozilla/5.0'},timeout=6)
        r.raise_for_status()
        for x in r.json().get('quotes',[]):
            if x.get('quoteType') not in ('EQUITY','ETF') or x.get('exchange') not in ('NMS','NGM','NCM','NYQ','ASE','PCX','BTS'): continue
            s=x.get('symbol','')
            try: s=store.symbol(s)
            except ValueError: continue
            store.register({'symbol':s,'name':x.get('shortname') or x.get('longname') or s,'en':x.get('longname') or '', 'exchange':x.get('exchDisp') or x['exchange'],'asset_type':'ETF' if x['quoteType']=='ETF' else '股票'})
        return {'items':store.search(q),'source':'local+Yahoo','message':'目录匹配不保证行情源当前可用；仅收录美股/ETF，未接入加密现货'}
    except Exception: return {'items':local,'source':'local','message':'在线目录暂不可用，保留本地匹配结果'}

@router.post('/watchlist')
def save_watch(body:Watch): return invoke(store.save_watch,invoke(store.symbol,body.symbol),body.direction,body.note,body.tag_ids,body.version)
@router.delete('/watchlist/{symbol}')
def delete_watch(symbol:str,version:int=Query(ge=1)):
    invoke(store.remove_watch,symbol,version);return {'ok':True}
@router.post('/tags')
def add_tag(body:Tag): return invoke(store.add_tag,body.name)
@router.delete('/tags/{tid}')
def delete_tag(tid:int): store.delete_tag(tid);return {'ok':True}
@router.get('/plans')
def plans(): return {'items':store.list_plans()}
@router.post('/plans')
def create_plan(body:Plan):
    if body.mode == 'swing' and body.direction == 'long' and body.stop_pct > formation_rules.HARD_STOP_PCT:
        raise HTTPException(400, f'多头波段价格止损比例不得超过{formation_rules.HARD_STOP_PCT}%')
    values=body.model_dump(mode='json');values['symbol']=invoke(store.symbol,values['symbol'])
    return {'id':invoke(store.create_plan,values)}
@router.post('/plans/{pid}/close')
def close_plan(pid:int,body:Version): invoke(store.close_plan,pid,body.version,body.review);return {'ok':True}
@router.get('/export')
def export(): return {'version':3,'exported_at':store.now(),'watchlist':store.watchlist(),'tags':store.tags(),'plans':store.list_plans()}

@router.get('/fundamentals/{symbol}')
def fundamentals(symbol: str):
    """Official SEC filing facts, deliberately separate from the price pipeline."""
    s = invoke(store.symbol, symbol)
    if not store.instrument(s):
        raise HTTPException(404, '标的不在证券目录，请先搜索')
    try:
        return sec_edgar.company_fundamentals(s)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except sec_edgar.EdgarUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

@router.get('/gold-watch')
def gold_watch(refresh: bool = False):
    """Dated Federal Reserve macro checks for an in-app gold research prompt."""
    if demo_market.enabled():
        raise HTTPException(503,'演示模式仅提供样例：黄金宏观数据需要在联网模式查询')
    try:
        return gold_signal.current(force=refresh)
    except gold_signal.GoldDataUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

@router.get('/market-pulse')
def market_pulse_snapshot(refresh: bool = False):
    """Original QQQ temperature formula and separately sourced Cboe VIX."""
    return market_pulse.current(force=refresh)

RULES={
 'version':'user-docs-20260927-review1',
 'formation_rule_version':formation_rules.RULE_VERSION,
 'formation_hard_stop_pct':formation_rules.HARD_STOP_PCT,
 'swing':{'title':'波段战法','scope':'日线参考；两条入场分支独立研究','rules':[
  {'title':'环境先行','detail':'先看大盘位置与环境，再看行业板块，最后看个股。当前指数指标是环境参考，不冒充涨跌家数温度。','state':'reference'},
  {'title':'近3至5日低价区','detail':'展示此前3/5个已完成交易日低点和价格距离；接近容差、企稳条件未确认，不直接生成买入信号。','state':'reference'},
  {'title':'首次回踩均线','detail':'MA5/MA10/MA20可查看；趋势起点、首次计数和确认口径待确定。','state':'pending'},
  {'title':'3570与3221','detail':'3570依市场状态分层建仓，3221按实际成交记录分层止盈。20%按实际成本计算；已设置的更紧保护价沿用。请在阵型面板核对。','state':'reference'}]},
 'intraday':{'title':'超短线战法','scope':'盘中结构参考，价格/时间/逻辑退出分别管理','rules':[
  {'title':'开盘观察','detail':'原文美股开盘后3至15分钟。用纽约时间显示；盘前盘后、节假日状态以行情与交易日历核验，不仅依电脑时钟判定开市。','state':'reference'},
  {'title':'V/W/M形态','detail':'原文V/W为候选，M/下降结构回避做多；阈值和确认算法未定义，当前不输出自动形态买点。','state':'pending'},
  {'title':'仓位与加仓','detail':'原文单笔≤5%，途中不加仓；总超短预算和多笔累计上限还需确认。','state':'reference'},
  {'title':'三类退出','detail':'价格止损1.5%至最多3%应在计划中选定；原文T+3兑现、T+5期限，时间优先级和交易日口径待确认。','state':'reference'},
  {'title':'分批止盈','detail':'3%至5%卖一半、7%再卖一半、10%全卖；“一半”以原始还是剩余仓位计算尚未明确。','state':'pending'}]}}
@router.get('/rules')
def rules(): return RULES

@router.get('/formations')
def formations():
    return formation_rules.rulebook()

@router.post('/formations/evaluate')
def evaluate_formation(body: dict):
    return invoke(formation_rules.evaluate, body)

# Signals here are factual checks with explicit, fixed calculation windows. They are not trading orders.
def frame(raw):
    if raw is None or len(raw)<10: raise ValueError('行情不足，至少需要10根K线')
    d=raw.copy();d=d[~d.index.duplicated(keep='last')].sort_index()
    cols=['open','high','low','close','volume']
    for c in cols: d[c]=pd.to_numeric(d[c],errors='coerce')
    d=d.replace([np.inf,-np.inf],np.nan).dropna(subset=cols)
    d=d[(d['close']>0)&(d['low']>0)&(d['high']>=d['low'])&(d['volume']>=0)]
    if len(d)<10: raise ValueError('有效行情不足')
    return add_indicators(d)

def rows(d):
    cols=['open','high','low','close','volume','MA5','MA10','MA20','MA60','K','D','J','RSI','DIF','DEA','MACD']
    return clean([{'time':pd.Timestamp(t).isoformat(),**{k.lower():r[k] for k in cols if k in r}} for t,r in d.tail(180).iterrows()])

def build_analysis(s,period,index):
    started=store.now();meta=store.instrument(s)
    if not meta or not meta['verified']: raise ValueError('旧代码尚未识别，请先在搜索中核验后再分析')
    # Preserve dotted share-class symbols. Data providers apply their own mapping.
    if meta['exchange'] in ('NASDAQ','NYSE'): dp._TV_EXCHANGE_HINT[s]=meta['exchange']
    elif meta['exchange'] in ('NYSE Arca','NYSEArca','AMEX'): dp._TV_EXCHANGE_HINT[s]='AMEX'
    raw=dp.get_daily(s,1000);daily=frame(raw)
    daily_source=raw.attrs.get('data_source',dp.source_label('daily',s))
    adjustment='split' if daily_source.startswith('Alpaca') else '供应商复权口径待独立核验'
    dataset_id=research_store.save_dataset(s,raw,daily_source,adjustment)
    decision=trade_engine.decision(raw,daily_source)
    decision.update(dataset_id=dataset_id,adjustment=adjustment)
    warnings=[];idx=None
    try: idx=frame(dp.get_index_daily(index,220))
    except Exception: warnings.append('大盘数据暂不可用，个股图表仍可查看')
    resonance = None
    if period=='daily':
        chart=daily;source=daily_source
        resonance=resonance_v1.evaluate(raw,daily_source,adjustment)
    elif period=='weekly':
        source=f'{daily_source} · 日线合成'
        chart,resonance=resonance_v1.evaluate_weekly(raw,source,adjustment)
        if chart.empty:
            raise ValueError('有效已收盘周线不足')
    else:
        getter={'monthly':lambda:dp.get_monthly(s,1800),'intraday':lambda:dp.get_intraday(s)}[period]
        chart=frame(getter());source=dp.source_label(period,s)
    last=daily.iloc[-1];pre=daily.iloc[-2]
    low3=float(daily['low'].iloc[-4:-1].min());low5=float(daily['low'].iloc[-6:-1].min())
    today=datetime.now(NY).date();lastdate=pd.Timestamp(daily.index[-1]).date()
    prior_volume=daily['volume'].iloc[-21:-1].mean()
    checks=[{'name':'收盘相对MA5','value':float(last['Dev5']),'unit':'%','detail':'(最近日线收盘 / MA5 − 1) × 100%','state':'pass' if last['close']>=last['MA5'] else 'wait'},
     {'name':'J值（最近日线）','value':float(last['J']),'unit':'','detail':'J<0为旧战法超卖参考，不代表两份新战法的买点','state':'reference'},
     {'name':'距离此前5日低点','value':(float(last['close'])/low5-1)*100,'unit':'%','detail':'不含当前日线；候选容差与止跌确认未定义','state':'reference'},
     {'name':'当日量比参考','value':float(last['volume']/prior_volume) if prior_volume>0 else None,'unit':'倍','detail':'最近日线量 / 此前20交易日均量；不是3/7日内巨量事件','state':'reference'}]
    market=None
    if idx is not None:
        il=idx.iloc[-1];market={'symbol':index,'as_of':str(idx.index[-1]),'source':dp.source_label('daily',index),'price':il['close'],'change_pct':(il['close']/idx.iloc[-2]['close']-1)*100,'ma20':il['MA20'],'above_ma20':bool(il['close']>=il['MA20']),'rsi':il['RSI'],'history':[{'time':str(t),'close':r['close']} for t,r in idx.tail(60).iterrows()]}
        if pd.Timestamp(idx.index[-1]).date()!=lastdate: warnings.append('指数与个股最后交易日期不同，环境对照需谨慎')
    if period=='intraday':
        warnings.append('分钟数据可能包含盘前盘后；形态算法未确认，不自动输出V/W买点')
        tz_label='America/New_York' if source.startswith(('TradingView','Finnhub','Yahoo')) else '供应商原始时区，待核验'
    elif period=='weekly': tz_label='美股每周最后一个交易日'
    else: tz_label='交易日期标签'
    if lastdate>=today: warnings.append('最近日线可能尚未收盘，指标会变化')
    if idx is not None and decision.get('available'):
        stock_done,_=trade_engine.completed(daily)
        index_done,_=trade_engine.completed(idx)
        common=stock_done.index.intersection(index_done.index)
        if len(common)>=21 and common[-1]==stock_done.index[-1]==index_done.index[-1]:
            stock_return=float(stock_done.loc[common[-1],'close']/stock_done.loc[common[-21],'close']-1)*100
            index_return=float(index_done.loc[common[-1],'close']/index_done.loc[common[-21],'close']-1)*100
            decision['relative_strength']={'benchmark':index,'stock_return_20':stock_return,'index_return_20':index_return,'excess_pct_points':stock_return-index_return,'as_of':str(common[-1].date()),'note':'20个共同交易日价格相对强弱，不是资金流量'}
    data={'instrument':meta,'period':period,'rule_version':RULES['version'],'fetched_at':store.now(),'started_at':started,'as_of':pd.Timestamp(chart.index[-1]).isoformat(),'daily_as_of':pd.Timestamp(daily.index[-1]).isoformat(),'timezone':tz_label,'source':source,'daily_source':daily_source,'adjustment':adjustment,'is_live':False,'chart':rows(chart),'decision':decision,'swing_plan':{**swing_playbook.decision(raw,daily_source),'dataset_id':dataset_id,'adjustment':adjustment},'confluence':swing_confluence.evaluate(daily),'market':market,'checks':checks,'metrics':{'price':last['close'],'change_pct':(last['close']/pre['close']-1)*100,'ma5':last['MA5'],'ma10':last['MA10'],'ma20':last['MA20'],'rsi':last['RSI'],'j':last['J'],'low3':low3,'low5':low5,'ma5_discipline':last['MA5']*.925,'volume':last['volume']},'warnings':warnings,'limitations':['板块前提尚未接入，不能视为已通过','图表与指标属于技术观察；3570、3221请在独立阵型面板核对实际成交进度']}
    if resonance is not None:
        data['resonance']=resonance
    data=clean(data);store.put_snapshot(f'{s}:{period}:{index}',data);return data

def job_run(key,s,period,index):
    try:
        result=build_analysis(s,period,index)
        with LOCK: JOBS[key]={'state':'ready','updated':time.monotonic(),'error':None}
        return result
    except Exception as e:
        # Provider exceptions can contain URLs / credentials. Do not return their contents.
        error=str(e) if isinstance(e,ValueError) and str(e).startswith(('行情','有效','旧代码')) else '行情源暂不可用或请求失败，请稍后重试'
        with LOCK: JOBS[key]={'state':'error','updated':time.monotonic(),'error':error}

def weekly_snapshot(cache, symbol):
    """Convert a legacy snapshot using the daily data saved with that snapshot."""
    if cache.get('period') == 'weekly' and (cache.get('resonance') or {}).get('period') == 'weekly':
        return cache
    dataset_id=(cache.get('decision') or {}).get('dataset_id')
    if not dataset_id:
        return None
    try:
        raw,meta=research_store.dataset(symbol,dataset_id)
        source=f"{meta['source']} · 日线合成"
        chart,result=resonance_v1.evaluate_weekly(raw,source,meta['adjustment'])
    except ValueError:
        return None
    if chart.empty:
        return None
    return {**cache, 'period':'weekly', 'chart':rows(chart),
            'source':source, 'as_of':pd.Timestamp(chart.index[-1]).isoformat(),
            'timezone':'美股每周最后一个交易日', 'resonance':clean(result)}


def restore_chart_resonance(cache, symbol):
    period=cache.get('period')
    if period not in ('daily','weekly'):
        return
    result=cache.get('resonance')
    if not result and period=='daily':
        # Rebuild old snapshots from their own immutable dataset, never the latest dataset of another date.
        dataset_id=(cache.get('decision') or {}).get('dataset_id')
        if dataset_id:
            try:
                raw, meta=research_store.dataset(symbol,dataset_id)
                result=resonance_v1.evaluate(raw,meta['source'],meta['adjustment'])
                cache['resonance']=result
            except ValueError:
                return
    if result and result['available']:
        check=weekly_freshness if period=='weekly' else freshness
        current=check(result['as_of'])
        result['quality'].update(current)
        if not current['fresh']:
            result['latest_signals']=[]


@router.get('/analysis/{symbol}')
def analysis(symbol:str,period:Literal['daily','weekly','monthly','intraday']='daily',index:Literal['QQQ','SPY','DIA']='QQQ',refresh:bool=False):
    s=invoke(store.symbol,symbol)
    if not store.instrument(s): raise HTTPException(404,'标的不在证券目录，请先搜索')
    key=f'{s}:{period}:{index}';cache=store.snapshot(key)
    if period=='weekly':
        daily_cache=store.snapshot(f'{s}:daily:{index}')
        original=cache
        if daily_cache and (daily_cache.get('daily_as_of') or '') > ((cache or {}).get('daily_as_of') or ''):
            original=daily_cache
        if original:
            cache=weekly_snapshot(original,s) or cache
    if cache and cache.get('decision'):
        decision=cache['decision']
        q=freshness(decision.get('as_of'))
        decision['quality'].update(q)
        decision['current_eligible']=bool(q['fresh'] and decision['quality'].get('valid'))
        if not decision['current_eligible']:
            for side in decision.get('sides',{}).values():
                side.update(triggered=False,sizing=None,status='数据待核验 · 暂停当前提示')
    if cache and cache.get('swing_plan'):
        plan=cache['swing_plan'];q=freshness(plan.get('as_of'))
        plan['quality'].update(q)
        plan['current_eligible']=bool(q['fresh'] and plan['quality'].get('valid'))
        if not plan['current_eligible']:
            for side in plan.get('sides',{}).values():
                side.update(triggered=False,stage='observe',sizing=None,status='数据待核验 · 暂停当前提示')
    if cache:
        restore_chart_resonance(cache, s)
    if cache and cache.get('confluence'):
        try:
            if not freshness(cache['confluence']['as_of'])['fresh']:
                cache['confluence'].update(stale=True,state='stale',latest_signal=None)
        except (ValueError,TypeError,KeyError):
            cache['confluence'].update(stale=True,state='stale',latest_signal=None)
    with LOCK:
        job=JOBS.get(key)
        if job and job['state']=='loading': pass
        elif refresh or not job or (time.monotonic()-job['updated']>300):
            if sum(j['state']=='loading' for j in JOBS.values())>=6:
                return {'state':'busy','data':cache,'from_cache':bool(cache),'error':'已有多个行情任务，请稍后再试'}
            if refresh:
                dp.clear_failed_cache(s)
                dp.clear_failed_cache(index)
            JOBS[key]={'state':'loading','updated':time.monotonic(),'error':None};POOL.submit(job_run,key,s,period,index)
            job=JOBS[key]
        state=job['state'] if job else 'loading'
        error=job.get('error') if job else None
    return {'state':state,'data':cache,'from_cache':state!='ready' and cache is not None,'error':error}

@router.get('/status')
def status():
    with LOCK: jobs=[{'key':k,'state':v['state'],'error':v.get('error')} for k,v in JOBS.items()]
    return {**store.status(),'version':'3.3.0','jobs':jobs,'server_time':store.now(),'new_york_time':datetime.now(NY).isoformat(),'auto_orders':False,'alpaca':dp.alpaca_data.status(),'research_records':research_store.records()}
