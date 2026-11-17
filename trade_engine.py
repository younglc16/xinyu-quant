"""Versioned research rules, risk sizing and next-open backtest; no order adapter."""
from __future__ import annotations
import hashlib,json,math
import numpy as np
import pandas as pd
from market_clock import completed,calendar

VERSION='turtle55-20-close-v1'
DEFAULTS={'equity':100000.,'risk_pct':0.5,'position_pct':10.,'fee_bps':2.,'slippage_bps':5.,'borrow_pct':8.}

def parameters(values=None):
    p={**DEFAULTS,**(values or {})}
    bounds={'equity':(100,1e9),'risk_pct':(.01,5),'position_pct':(.1,100),'fee_bps':(0,100),'slippage_bps':(0,200),'borrow_pct':(0,200)}
    for k,(lo,hi) in bounds.items():
        v=float(p[k])
        if not math.isfinite(v) or not lo<=v<=hi: raise ValueError('研究参数超出允许范围：'+k)
        p[k]=v
    if set(p)!=set(bounds): raise ValueError('未知研究参数')
    return p

def prepare(raw,now=None):
    d,status=completed(raw,now)
    cols=['open','high','low','close','volume']
    d=d[cols].apply(pd.to_numeric,errors='coerce').sort_index()
    duplicate=int(d.index.normalize().duplicated().sum())
    d=d[~d.index.normalize().duplicated(keep='last')]
    valid=np.isfinite(d).all(axis=1)&(d[['open','high','low','close']]>0).all(axis=1)&(d.volume>=0)&(d.high>=d[['open','close','low']].max(axis=1))&(d.low<=d[['open','close','high']].min(axis=1))
    invalid=int((~valid).sum());d=d.loc[valid]
    status.update(invalid_rows=invalid,duplicate_rows=duplicate,rows=len(d),fresh=False,missing_sessions=0)
    if len(d):
        d.index=d.index.normalize()
        status['as_of']=str(d.index[-1].date());status['fresh']=status['as_of']==status['expected_session']
        expected=calendar().sessions_in_range(d.index[0],d.index[-1])
        status['missing_sessions']=int(len(expected.difference(d.index)))
        status['unexpected_sessions']=int(len(d.index.difference(expected)))
    status['valid']=len(d)>=80 and not(invalid or duplicate or status['missing_sessions'] or status.get('unexpected_sessions',0))
    return d,status

def features(d):
    d=d.copy();prev=d.close.shift(1)
    tr=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
    atr=np.full(len(d),np.nan)
    if len(d)>=20:
        atr[19]=tr.iloc[:20].mean()
        for i in range(20,len(d)): atr[i]=(atr[i-1]*19+tr.iloc[i])/20
    d['atr']=atr
    for n in (55,20):
        d[f'high{n}']=d.high.shift(1).rolling(n).max()
        d[f'low{n}']=d.low.shift(1).rolling(n).min()
    # Entry is evaluated at close; all thresholds exclude the current bar.
    d['signal']=np.where(d.close>d.high55,1,np.where(d.close<d.low55,-1,0))
    d['volume_ratio']=d.volume/d.volume.shift(1).rolling(20).mean().replace(0,np.nan)
    return d

def digest(d):
    return hashlib.sha256(d[['open','high','low','close','volume']].to_csv(float_format='%.10g',date_format='%Y-%m-%d').encode()).hexdigest()

def size(entry,atr,p):
    distance=2*atr;budget=p['equity']*p['risk_pct']/100
    round_cost=entry*2*(p['fee_bps']+p['slippage_bps'])/10000
    shares=max(0,math.floor(min(budget/(distance+round_cost),p['equity']*p['position_pct']/100/entry))) if entry>0 and distance>0 else 0
    return {'shares':shares,'notional':shares*entry,'stop_risk':shares*distance,'estimated_round_cost':shares*round_cost,
            'planned_loss':shares*(distance+round_cost),'risk_budget':budget,'position_pct':shares*entry/p['equity']*100,
            'note':'整数股；含双边费用与滑点预算，不含跳空超损及持仓期借券费'}

def decision(raw,source,values=None,now=None):
    p=parameters(values);d,q=prepare(raw,now)
    out={'version':VERSION,'quality':q,'parameters':p,'source':source,'available':False,'current_eligible':False}
    if len(d)<80: return {**out,'reason':'至少需要80根有效、已完成日线'}
    f=features(d);r=f.iloc[-1];atr=float(r.atr)
    if not math.isfinite(atr) or atr<=0:return {**out,'reason':'ATR不可用'}
    out.update(available=True,current_eligible=q['valid'] and q['fresh'],as_of=q['as_of'],data_hash=digest(d),bars=len(d),atr=atr,close=float(r.close),volume_ratio=float(r.volume_ratio) if pd.notna(r.volume_ratio) else None)
    sides={}
    for name,sign in [('long',1),('short',-1)]:
        triggered=int(r.signal)==sign
        threshold=float(r.high55 if sign==1 else r.low55)
        upcoming=float(d.high.tail(55).max() if sign==1 else d.low.tail(55).min())
        entry=float(r.close) if triggered else upcoming
        stop=entry-sign*2*atr
        sensible=entry>0 and stop>0
        status='收盘突破已出现' if triggered else '等待收盘突破'
        if not out['current_eligible']:status='数据待核验 · 暂停当前提示'
        sides[name]={'direction':name,'triggered':triggered and out['current_eligible'],'historical_breakout':triggered,'status':status,
            'entry':entry,'signal_threshold':threshold,'next_threshold':upcoming,'stop':stop,'target2r':entry+sign*4*atr if entry+sign*4*atr>0 else None,'target3r':entry+sign*6*atr if entry+sign*6*atr>0 else None,
            'channel_exit':float(d.low.tail(20).min() if sign==1 else d.high.tail(20).max()),
            'sizing':size(entry,atr,p) if sensible and out['current_eligible'] else None,
            'entry_note':'已突破时以收盘价估算，实际下一开盘需重算；未突破时为下一日观察阈值',
            'execution_checks':['借券可得性待确认','实际借券费待确认','Reg SHO价格限制待确认','财报与除息待确认'] if sign==-1 else ['财报与重大事件待确认','下一开盘跳空与价格待确认']}
    out['sides']=sides
    ma20=float(d.close.tail(20).mean())
    out['evidence']={'ma20':ma20,'trend':'收盘在20日均线上方' if r.close>=ma20 else '收盘在20日均线下方','volume':'量能超过此前20日均量' if pd.notna(r.volume_ratio) and r.volume_ratio>=1 else '量能未达此前20日均量；突破需谨慎','long_case':'收盘上破55日高点，观察趋势延续；跌破退出价则假设失效','short_case':'收盘下破55日低点，观察下行延续；上破退出价则假设失效'}
    out['signals']=[{'time':str(t.date()),'direction':'long' if row.signal==1 else 'short','kind':'turtle'} for t,row in f.iloc[-180:].iterrows() if row.signal and row.signal!=f.signal.shift(1).loc[t]]
    return out

def _metrics(curve,trades,initial,costs,turnover,exposure,baseline):
    e=np.array([initial]+[x['equity'] for x in curve],dtype=float);returns=e[1:]/e[:-1]-1
    peak=np.maximum.accumulate(e);dd=e/peak-1
    days=max(1,(pd.Timestamp(curve[-1]['date'])-pd.Timestamp(curve[0]['date'])).days) if curve else 1
    pnl=[t['net_pnl'] for t in trades];wins=sum(x for x in pnl if x>0);losses=-sum(x for x in pnl if x<0)
    vol=float(np.std(returns,ddof=1)) if len(returns)>1 else 0
    return {'return_pct':(e[-1]/initial-1)*100,'cagr_pct':((e[-1]/initial)**(365.25/days)-1)*100 if e[-1]>0 else -100,
       'max_drawdown_pct':float(dd.min()*100),'volatility_pct':vol*np.sqrt(252)*100,
       'sharpe':float(np.mean(returns)/vol*np.sqrt(252)) if vol>0 else None,'trades':len(pnl),
       'long_trades':sum(t['direction']=='long' for t in trades),'short_trades':sum(t['direction']=='short' for t in trades),
       'win_rate_pct':sum(x>0 for x in pnl)/len(pnl)*100 if pnl else None,'profit_factor':wins/losses if losses else None,
       'turnover':turnover/initial,'exposure_pct':exposure/max(1,len(curve))*100,'costs':costs,
       'baseline_return_pct':(baseline/initial-1)*100,'end_equity':e[-1]}

def simulate(f,p,start):
    cash=p['equity'];pos=None;trades=[];curve=[];costs=0.;turnover=0.;exposure=0
    slip=p['slippage_bps']/10000;fee=p['fee_bps']/10000;baseline_shares=0;baseline_cash=cash
    for i in range(start,len(f)):
        r=f.iloc[i];prev=f.iloc[i-1];day=f.index[i];
        if i==start:
            price=float(r.open)*(1+slip);baseline_shares=math.floor(cash*p['position_pct']/100/(price*(1+fee)));baseline_cash=cash-baseline_shares*price*(1+fee)
        if pos and pos['sign']==-1:
            elapsed=(day-pos['charged_to']).days
            charge=pos['qty']*float(prev.close)*p['borrow_pct']/100*elapsed/365
            cash-=charge;pos['borrow']+=charge;costs+=charge;pos['charged_to']=day
        if pos:
            channel=float(r.low20 if pos['sign']==1 else r.high20)
            pos['exit_level']=max(pos['exit_level'],channel) if pos['sign']==1 else min(pos['exit_level'],channel)
        if not pos and cash>0 and prev.signal:
            sign=int(prev.signal);entry=float(r.open)*(1+sign*slip)
            calc=size(entry,float(prev.atr),{**p,'equity':cash});qty=calc['shares']
            if qty and entry-sign*2*float(prev.atr)>0:
                entry_fee=qty*entry*fee;cash-=entry_fee;costs+=entry_fee+qty*abs(entry-float(r.open));turnover+=qty*entry
                pos={'sign':sign,'qty':qty,'entry':entry,'entry_date':str(day.date()),'signal_date':str(f.index[i-1].date()),'entry_fee':entry_fee,'borrow':0.,'charged_to':day,'exit_level':entry-sign*2*float(prev.atr)}
                channel=float(r.low20 if sign==1 else r.high20)
                pos['exit_level']=max(pos['exit_level'],channel) if sign==1 else min(pos['exit_level'],channel)
        if pos:
            exposure+=1;sign=pos['sign'];level=pos['exit_level']
            hit=(float(r.low)<=level) if sign==1 else (float(r.high)>=level)
            final=i==len(f)-1
            if hit or final:
                rawprice=(min(float(r.open),level) if sign==1 else max(float(r.open),level)) if hit else float(r.close)
                fill=rawprice*(1-sign*slip);exitfee=pos['qty']*fill*fee
                gross=pos['qty']*sign*(fill-pos['entry']);cash+=gross-exitfee
                costs+=exitfee+pos['qty']*abs(fill-rawprice);turnover+=pos['qty']*fill
                trades.append({'direction':'long' if sign==1 else 'short','signal_date':pos['signal_date'],'entry_date':pos['entry_date'],'exit_date':str(day.date()),'entry':pos['entry'],'exit':fill,'shares':pos['qty'],'net_pnl':gross-pos['entry_fee']-exitfee-pos['borrow'],'borrow_cost':pos['borrow'],'reason':'止损/20日通道' if hit else '样本末平仓'})
                pos=None
        equity=cash+(pos['qty']*pos['sign']*(float(r.close)-pos['entry']) if pos else 0)
        base=baseline_cash+baseline_shares*float(r.close)
        if i==len(f)-1:base=baseline_cash+baseline_shares*float(r.close)*(1-slip)*(1-fee)
        curve.append({'date':str(day.date()),'equity':equity,'baseline':base})
    return {'metrics':_metrics(curve,trades,p['equity'],costs,turnover,exposure,curve[-1]['baseline']),'curve':curve,'trades':trades,'from':curve[0]['date'],'to':curve[-1]['date']}

def backtest(raw,source,values=None,now=None):
    p=parameters(values);d,q=prepare(raw,now)
    if len(d)<200:raise ValueError('回测至少需要200根已完成日线')
    if not q['valid']:raise ValueError('日线存在缺失、重复或异常价格，先核验数据再回测')
    f=features(d);cut=max(80,int(len(d)*.7));full=simulate(f,p,56);holdout=simulate(f,p,cut)
    return {'version':VERSION,'data_hash':digest(d),'source':source,'quality':q,'parameters':p,'bars':len(d),'full':full,'holdout':holdout,
      'limitations':['单标的历史研究，存在选择与幸存者偏差；未扫描全市场','后30%为固定参数时间留出检验，未做训练或参数寻优','拆股/分红按供应商口径；未模拟分红现金流和做空分红补偿','借券费为假设，未还原券源、逼空、停牌和Reg SHO成交约束','日线无法还原逐笔成交；止损不能保证最大亏损','少于30笔交易时不作稳健性结论；过去表现不预测未来收益']}
