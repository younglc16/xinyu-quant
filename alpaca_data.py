"""Optional, read-only SIP historical bars. No brokerage API or silent IEX downgrade."""
import os
from datetime import datetime,timedelta,timezone
import pandas as pd
import requests

def configured():return bool(os.getenv('APCA_API_KEY_ID') and os.getenv('APCA_API_SECRET_KEY'))

def status():
    return {'configured':configured(),'feed':'sip','adjustment':'split','scope':'只读历史日线，非实时行情','documentation':'https://docs.alpaca.markets/us/reference/stockbars'}

def daily(symbol,days=1000,session=None):
    if not configured():raise ValueError('Alpaca密钥未配置')
    end=datetime.now(timezone.utc)-timedelta(minutes=16)
    params={'symbols':symbol,'timeframe':'1Day','start':(end-timedelta(days=max(120,int(days*1.7)+30))).isoformat(),'end':end.isoformat(),'feed':'sip','adjustment':'split','limit':10000,'sort':'asc'}
    headers={'APCA-API-KEY-ID':os.environ['APCA_API_KEY_ID'],'APCA-API-SECRET-KEY':os.environ['APCA_API_SECRET_KEY']}
    get=(session or requests).get;rows=[];seen=set()
    for _ in range(10):
        response=get('https://data.alpaca.markets/v2/stocks/bars',params=params,headers=headers,timeout=(5,15))
        if response.status_code!=200:raise ValueError('Alpaca历史行情失败，请检查权限、限流或服务状态')
        data=response.json();rows.extend(data.get('bars',{}).get(symbol,[]));token=data.get('next_page_token')
        if not token:break
        if token in seen:raise ValueError('Alpaca分页异常')
        seen.add(token);params['page_token']=token
    else:raise ValueError('Alpaca分页超出限制')
    if not rows:raise ValueError('Alpaca没有返回日线')
    frame=pd.DataFrame(rows).rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume'})
    frame.index=pd.to_datetime(frame.pop('t'),utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
    return frame[['open','high','low','close','volume']].astype(float).sort_index().tail(days)
