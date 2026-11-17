"""Local research endpoints. No credentials, orders or external writes."""
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field,ConfigDict
import trade_engine as engine
import swing_playbook
import research_store as records
import v3_store as store

router=APIRouter(prefix='/api/v3/research')
records.init()
class Parameters(BaseModel):
    model_config=ConfigDict(extra='forbid')
    equity:float=Field(default=100000,ge=100,le=1e9,allow_inf_nan=False)
    risk_pct:float=Field(default=.5,ge=.01,le=5,allow_inf_nan=False)
    position_pct:float=Field(default=10,ge=.1,le=100,allow_inf_nan=False)
    fee_bps:float=Field(default=2,ge=0,le=100,allow_inf_nan=False)
    slippage_bps:float=Field(default=5,ge=0,le=200,allow_inf_nan=False)
    borrow_pct:float=Field(default=8,ge=0,le=200,allow_inf_nan=False)

def load(symbol):
    try:return records.dataset(store.symbol(symbol))
    except ValueError as e:raise HTTPException(400,str(e)) from e

@router.post('/decision/{symbol}')
def decision(symbol:str,body:Parameters):
    d,meta=load(symbol)
    out=engine.decision(d,meta['source'],body.model_dump());out['dataset_id']=meta['id'];out['adjustment']=meta['adjustment'];out['checked_at']=meta['checked_at']
    return out

@router.post('/setups/{symbol}')
def save_setup(symbol:str,body:Parameters):
    out=decision(symbol,body)
    if not out['current_eligible']:raise HTTPException(409,'数据过期或不完整，暂不保存当前交易测算')
    return {'id':records.record('setup',store.symbol(symbol),out['dataset_id'],out),'data':out}

@router.post('/backtests/{symbol}')
def backtest(symbol:str,body:Parameters):
    d,meta=load(symbol)
    try:out=engine.backtest(d,meta['source'],body.model_dump())
    except ValueError as e:raise HTTPException(400,str(e)) from e
    out['dataset_id']=meta['id'];out['adjustment']=meta['adjustment']
    out['id']=records.record('backtest',store.symbol(symbol),meta['id'],out)
    return out

@router.get('/records')
def history(symbol:str|None=None):
    if symbol:
        try:symbol=store.symbol(symbol)
        except ValueError as e:raise HTTPException(400,str(e)) from e
    return {'items':records.records(symbol)}

@router.get('/records/{ident}')
def detail(ident:str):
    try:return records.detail(ident)
    except ValueError as e:raise HTTPException(404,str(e)) from e

@router.get('/plan-risk')
def plan_risk():
    active=[x for x in store.list_plans() if x['status']=='active']
    long=sum(x['cost']*x['quantity'] for x in active if x['direction']=='long')
    short=sum(x['cost']*x['quantity'] for x in active if x['direction']=='short')
    return {'plans':len(active),'long_notional':long,'short_notional':short,'gross_notional':long+short,'net_notional':long-short,'planned_stop_loss':sum(x['cost']*x['quantity']*x['stop_pct']/100 for x in active),'scope':'按手工研究计划成本估算；不是实盘持仓，未计跳空、费用和相关性'}


@router.post('/swing-decision/{symbol}')
def swing_decision(symbol:str,body:Parameters):
    d,meta=load(symbol)
    out=swing_playbook.decision(d,meta['source'],body.model_dump())
    out.update(dataset_id=meta['id'],adjustment=meta['adjustment'],checked_at=meta['checked_at'])
    return out

@router.post('/swing-setups/{symbol}')
def save_swing_setup(symbol:str,body:Parameters):
    out=swing_decision(symbol,body)
    if not out['current_eligible']:raise HTTPException(409,'数据过期或不完整，暂不保存当前波段测算')
    return {'id':records.record('swing-setup',store.symbol(symbol),out['dataset_id'],out),'data':out}
