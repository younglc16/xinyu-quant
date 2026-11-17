"""Annual filing series and explicit FCFF assumptions; no trading commands."""
from datetime import datetime,date,timezone
import math
import sec_edgar as sec

TAGS={
 'revenue':('RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet'),
 'net_income':('NetIncomeLoss','ProfitLoss'),
 'operating_cash_flow':('NetCashProvidedByUsedInOperatingActivities',),
 'capex':('PaymentsToAcquirePropertyPlantAndEquipment','PaymentsToAcquireProductiveAssets'),
 'operating_income':('OperatingIncomeLoss',),
 'cash':('CashAndCashEquivalentsAtCarryingValue',),
 'long_term_debt':('LongTermDebtNoncurrent','LongTermDebt'),
 'equity':('StockholdersEquity',),
}
DURATION={'revenue','net_income','operating_cash_flow','capex','operating_income'}


def annual_series(facts,as_of=None):
    cutoff=as_of or date.today().isoformat();gaap=facts.get('facts',{}).get('us-gaap',{});series={}
    for key,tags in TAGS.items():
        selected={}
        for priority,tag in enumerate(tags):
            for v in gaap.get(tag,{}).get('units',{}).get('USD',[]):
                if v.get('form') not in ('10-K','10-K/A') or not isinstance(v.get('val'),(int,float)) or isinstance(v.get('val'),bool) or not math.isfinite(v['val']):continue
                if not v.get('filed') or v['filed']>cutoff or v.get('end','')>cutoff:continue
                if key in DURATION:
                    try:days=(date.fromisoformat(v['end'])-date.fromisoformat(v['start'])).days
                    except (KeyError,ValueError):continue
                    if not 330<=days<=385:continue
                identity=(v.get('start') if key in DURATION else None,v.get('end'))
                rank=(v['filed'],-priority)
                if identity not in selected or rank>selected[identity][0]:selected[identity]=(rank,dict(v,tag=tag))
        series[key]={k:v[1] for k,v in selected.items()}
    revenues={}
    for (start,end),v in series['revenue'].items():
        if end not in revenues or v['filed']>revenues[end]['filed']:revenues[end]=v
    rows=[]
    cik=str(facts.get('cik','')).lstrip('0')
    for end,rev in sorted(revenues.items())[-6:]:
        row={'start':rev['start'],'end':end,'metrics':{},'provenance':{}}
        for key in TAGS:
            identity=(rev['start'] if key in DURATION else None,end)
            item=series[key].get(identity)
            row['metrics'][key]=item['val'] if item else None
            if item:
                acc=item.get('accn','');row['provenance'][key]={'tag':item['tag'],'filed':item['filed'],'form':item['form'],'accession':acc,'url':f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-", "")}/' if acc else None}
        m=row['metrics'];m['free_cash_flow']=m['operating_cash_flow']-m['capex'] if m['operating_cash_flow'] is not None and m['capex'] is not None else None
        m['net_margin']=100*m['net_income']/m['revenue'] if m['revenue'] and m['net_income'] is not None else None
        m['operating_margin']=100*m['operating_income']/m['revenue'] if m['revenue'] and m['operating_income'] is not None else None
        m['revenue_growth']=None;m['roe']=None
        if rows:
            prev=rows[-1];gap=(date.fromisoformat(end)-date.fromisoformat(prev['end'])).days
            if 330<=gap<=385:
                old=prev['metrics'];m['revenue_growth']=100*(m['revenue']/old['revenue']-1) if old['revenue'] and old['revenue']>0 else None
                if m['equity'] is not None and old['equity'] is not None and min(m['equity'],old['equity'])>0 and m['net_income'] is not None:m['roe']=100*m['net_income']/((m['equity']+old['equity'])/2)
        rows.append(row)
    rows=rows[-5:]
    contiguous=all(330<=(date.fromisoformat(b['end'])-date.fromisoformat(a['end'])).days<=385 for a,b in zip(rows,rows[1:]))
    return {'company':facts.get('entityName'),'rows':rows,'years_available':len(rows),'complete_five_years':len(rows)==5 and contiguous,'contiguous':contiguous,'issues':[] if contiguous else ['可比年度之间存在缺口，不应视为连续五年。'],'as_of':cutoff,'currency':'USD',
      'notice':'仅10-K及修订的完整年度；财年结束日可能不是12月。最新重述口径，非历史时点回测数据。FCF=经营现金流−资本开支；Capex沿申报标签，可能含无形资产，不自动跨公司比较或代入FCFF估值。长期债务非总债务；ROE非ROIC，ROIC口径待核验。'}


def fetch_annual(symbol):
    cik=sec._cik_for(symbol);url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'
    facts=sec._cached(f'facts:{cik}',lambda:sec._get(url))
    out=annual_series(facts);out.update(symbol=symbol,cik=f'{cik:010d}',source='SEC EDGAR Company Facts',source_url=url,fetched_at=datetime.now(timezone.utc).isoformat())
    return out


def valuation(p):
    """All money and share counts in millions; positive FCFF, WACC>g."""
    def value(key,lo=None,hi=None):
        v=p.get(key)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError(key+'须填写有限数字')
        if (lo is not None and v<lo) or (hi is not None and v>hi):raise ValueError(key+'超出允许范围')
        return v
    fcff=value('fcff',.000001,1e9);cash=value('cash',0,1e9);debt=value('debt',0,1e9);shares=value('shares',.000001,1e9)
    wacc=value('wacc',.1,100)/100;terminal=value('terminal',-10,10)/100
    if wacc<=terminal:raise ValueError('折现率WACC必须大于永续增长率')
    years=p.get('years')
    if type(years) is not int or years not in (5,10):raise ValueError('预测期须为5或10年')
    growths=[value(k,-80,100) for k in ('bear_growth','base_growth','bull_growth')]
    if growths!=sorted(growths):raise ValueError('增长假设应满足悲观≤基准≤乐观')
    cases=[]
    for name,growth in zip(('悲观','基准','乐观'),growths):
        f=fcff;pv=0;forecast=[]
        for year in range(1,years+1):
            f*=1+growth/100;discounted=f/(1+wacc)**year;pv+=discounted;forecast.append({'year':year,'fcff':f,'present_value':discounted})
        tv=f*(1+terminal)/(wacc-terminal);pv_tv=tv/(1+wacc)**years;ev=pv+pv_tv;eq=ev+cash-debt
        cases.append({'name':name,'growth_pct':growth,'enterprise_value':ev,'equity_value':eq,'per_share':eq/shares if eq>0 else None,'terminal_share_pct':pv_tv/ev*100,'forecast':forecast,'warning':'股权价值≤0，不产生正的每股价值' if eq<=0 else None})
    sensitivity=[]
    for delta in (-2,0,2):
        rate=wacc+delta/100
        if rate<=terminal or rate<=0:continue
        g=growths[1]/100;pv=sum(fcff*(1+g)**i/(1+rate)**i for i in range(1,years+1));tv=fcff*(1+g)**years*(1+terminal)/(rate-terminal)/(1+rate)**years
        sensitivity.append({'wacc_pct':rate*100,'per_share':max(0,(pv+tv+cash-debt)/shares)})
    pe=p['market_price']/p['eps'] if p.get('market_price') and p.get('eps') is not None and p['eps']>0 else None
    return {'pe':pe,'peer_pe':p.get('peer_pe'),'pe_basis':p.get('pe_basis'),'model':'FCFF企业价值DCF','money_unit':'百万美元；股数为百万股；每股值USD','assumptions':p,'cases':cases,'sensitivity':sensitivity,'notice':'情景估算，不是价格预测。假设由用户输入，未自动从OCF−Capex认定FCFF；未建模期权稀释、非经营资产及特殊金融公司。',
      'method_url':'https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/fcff.html'}
