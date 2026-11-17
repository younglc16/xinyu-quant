// Charts use only the selected API response. All four plots share one bar index.
const signalColors={long:'#f7dc62',short:'#ff8463'};
const escapeText=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function byDay(points){
 const dates=new Map();
 for(const point of points){
  if(!dates.has(point.time))dates.set(point.time,[]);
  dates.get(point.time).push(point);
 }
 return dates;
}
function resonanceText(s){
 const fmt=v=>Number.isFinite(v)?v.toFixed(2):'—';
 const direction=s.direction==='long'?'做多':'做空';
 const zone={low:'低位',mid:'中位',high:'高位'}[s.zone]||'—';
 const strength=s.strength==='strong'?'强':'中';
 const volume=s.volume_confirmed==null?'量能待核验':s.volume_confirmed?'量能达标':'量能未达';
 return `${s.time} ${direction}·${strength} ${s.rule_id} ${(s.events||[s.label]).join(' + ')}｜收 ${fmt(s.close)} · D ${fmt(s.d)}（${zone}） · VR3 ${fmt(s.vr3)} / VR7 ${fmt(s.vr7)} · ${volume} · 前提待核验`;
}
function signalGlyph(s,cx,cy){
 const long=s.direction==='long',color=signalColors[s.direction]||signalColors.short;
 if(s.kind==='turtle'){
  const points=long?'0,-6 -6,5 6,5':'0,6 -6,-5 6,-5';
  return `<g class="signal-marker" transform="translate(${cx} ${cy})"><title>${escapeText(s.time)} ${long?'做多':'做空'}55日突破观察</title><polygon points="${points}" fill="${color}" stroke="${color}"/><text x="0" y="${long?16:-9}" text-anchor="middle" fill="${color}" font-size="9">T${long?'多':'空'}</text></g>`;
 }
 const label=resonanceText(s);
 const height=long?5.5:-5.5;
 const points=`0,0 -3.8,${height} 3.8,${height}`;
 const fill=s.strength==='strong'?color:'#171713';
 return `<g class="signal-marker resonance-marker" data-direction="${long?'long':'short'}" data-rule="${escapeText(s.rule_id)}" data-date="${escapeText(s.time)}" transform="translate(${cx} ${cy})"><title>${escapeText(label)}</title><polygon points="${points}" fill="${fill}" stroke="${color}" stroke-width="1.15" stroke-linejoin="round"/><rect x="-5" y="${long?0:-8}" width="10" height="8" fill="transparent"/></g>`;
}
function crossGlyph(s,cx,cy){
 const gold=s.cross==='gold',color=signalColors[gold?'long':'short'];
 const path=gold?'M-2.8,0H2.8M0,-2.8V2.8':'M-2.1,-2.1L2.1,2.1M-2.1,2.1L2.1,-2.1';
 return `<g class="indicator-cross-marker" data-cross="${gold?'gold':'dead'}" transform="translate(${cx} ${cy})"><title>${escapeText(s.time)} ${escapeText(s.label)}</title><path d="${path}" fill="none" stroke="#171713" stroke-width="2.8" stroke-linecap="round"/><path d="${path}" fill="none" stroke="${color}" stroke-width="1.25" stroke-linecap="round"/></g>`;
}
export function drawCharts(root,all,{limit=90,bands=true,period='daily',signals=[],crosses=[],inspect=null,levels=[],compact=false}={}){
 const rows=all.slice(-limit);if(!rows.length){root.textContent='尚无可绘制的行情';return}
 const W=compact?Math.max(300,root.clientWidth):920,L=compact?7:12,R=compact?63:78,valid=v=>typeof v==='number'&&Number.isFinite(v),fmt=v=>valid(v)?v.toFixed(2):'—';root.innerHTML='';
 const markers=byDay(signals),crossMarkers=byDay(crosses);
 const height=compact?Math.max(180,root.clientHeight-87):0;
 const specs=[['price','价格与均线',compact?height*.55:290],['volume','成交量',compact?height*.12:76],['kdj','KDJ 随机指标 (9,3,3)',compact?height*.16:116],['macd','MACD 趋势动量 (12,26,9)',compact?height*.17:100]];
 const plots=[];
 const showSignals=period==='daily'||period==='weekly';
 for(const [type,title,H] of specs){
  let values=type==='price'?rows.flatMap(d=>[d.high,d.low,bands&&valid(d.ma5)?d.ma5*.925:null,d.ma5,d.ma10,d.ma20]):type==='volume'?rows.map(d=>d.volume):type==='kdj'?rows.flatMap(d=>[d.k,d.d,d.j,0,100]):rows.flatMap(d=>[d.dif,d.dea,d.macd,0]);if(type==='price'&&period==='daily')values.push(...levels.map(x=>x.price));values=values.filter(valid);if(!values.length)continue;
  let min=Math.min(...values),max=Math.max(...values),pad=(max-min||1)*(type==='price'&&showSignals?.18:.08);let lo=type==='volume'?0:min-pad,hi=max+pad;
  const x=i=>L+i*(W-L-R)/Math.max(1,rows.length-1),y=v=>H-7-(v-lo)/(hi-lo)*(H-18),bw=Math.max(3,(W-L-R)/rows.length*.68);
  const line=(key)=>{let pen=false;return rows.map((d,i)=>{let v=typeof key==='function'?key(d):d[key];if(!valid(v)){pen=false;return ''}let command=(pen?'L':'M')+x(i).toFixed(2)+','+y(v).toFixed(2);pen=true;return command}).join(' ')};
  let svg='';let ticks=type==='kdj'?(compact&&H<76?[20,80]:[0,20,80,100]):type==='macd'?[lo*.6,0,hi*.6]:type==='volume'?[hi*.7]:[lo+(hi-lo)*.15,(lo+hi)/2,lo+(hi-lo)*.85];
  for(const v of ticks){svg+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#3d402d"/><text x="${W-R+9}" y="${y(v)+4}" fill="#b7b99a" font-size="9">${type==='volume'?(v>=1e8?(v/1e8).toFixed(1)+'亿':(v/1e4).toFixed(0)+'万'):fmt(v)}</text>`;}
  if(type==='price'){
   if(bands)svg+=`<path d="${line(d=>valid(d.ma5)?d.ma5*.925:null)}" stroke="#e7783f" stroke-dasharray="5 5" fill="none"/>`;
   rows.forEach((d,i)=>{const c=d.close>=d.open?'#ff3b1f':'#62d1b2';const edge=d.close>=d.open?'#ffd18b':'#b4f3df';svg+=`<line x1="${x(i)}" x2="${x(i)}" y1="${y(d.high)}" y2="${y(d.low)}" stroke="${edge}" stroke-width="1.15"/><rect x="${x(i)-bw/2}" y="${Math.min(y(d.open),y(d.close))}" width="${bw}" height="${Math.max(2,Math.abs(y(d.close)-y(d.open)))}" fill="${c}" stroke="${edge}" stroke-width=".45"/>`;});
   for(const [key,c] of [['ma5','#e9ca68'],['ma10','#e89049'],['ma20','#b18cdd']])svg+=`<path d="${line(key)}" stroke="${c}" stroke-width="1.6" fill="none"/>`;
   if(period==='daily'){
    for(const level of levels){if(!valid(level.price)||level.price<=0)continue;const cy=y(level.price);svg+=`<line class="trade-level" x1="${L}" x2="${W-R}" y1="${cy}" y2="${cy}" stroke="${level.color}" stroke-dasharray="7 5"/><text x="${L+4}" y="${cy-5}" fill="${level.color}" font-size="9">${level.label} ${fmt(level.price)}</text>`;}
   }
   if(showSignals){
    rows.forEach((d,i)=>{
     for(const s of markers.get(d.time.slice(0,10))||[]){
      const isLong=s.direction==='long';
      const wickY=y(isLong?d.low:d.high);
      const cy=s.kind==='turtle'?Math.max(8,Math.min(H-8,wickY+(isLong?12:-12))):wickY;
      svg+=signalGlyph(s,x(i),cy);
     }
    });
   }
  }
  if(type==='volume'||type==='macd')rows.forEach((d,i)=>{const v=type==='volume'?d.volume:d.macd;if(!valid(v))return;const up=type==='volume'?d.close>=d.open:v>=0;const c=up?'#ff4c2b':'#62d1b2';svg+=`<rect x="${x(i)-bw/2}" y="${Math.min(y(v),y(0))}" width="${bw}" height="${Math.max(2,Math.abs(y(v)-y(0)))}" fill="${c}" stroke="#311007" stroke-width=".45"/>`});
  for(const [key,c] of (type==='kdj'?[['k','#ffe06b'],['d','#ff8b3d'],['j','#f2b2e8']]:type==='macd'?[['dif','#ffe06b'],['dea','#ff8b3d']]:[]))svg+=`<path d="${line(key)}" stroke="${c}" stroke-width="1.6" fill="none"/>`;
  if(showSignals&&(type==='kdj'||type==='macd')){
   const field=type==='kdj'?'k':'dif';
   rows.forEach((d,i)=>{
    for(const mark of crossMarkers.get(d.time.slice(0,10))||[]){
     if(mark.indicator===type&&valid(d[field]))svg+=crossGlyph(mark,x(i),Math.max(6,Math.min(H-6,y(d[field]))));
    }
   });
  }
  svg+=`<line class="cross" x1="${x(rows.length-1)}" x2="${x(rows.length-1)}" y1="0" y2="${H}"/>`;
  const panel=document.createElement('div');panel.className='plot';panel.innerHTML=`<div class="plot-head"><b>${title}</b><span></span></div><svg tabindex="0" role="img" aria-label="${title}，左右方向键逐根查看" viewBox="0 0 ${W} ${H}">${svg}</svg>`;root.append(panel);plots.push({type,panel,x});
  let cursor=rows.length-1;const node=panel.querySelector('svg');node.addEventListener('pointermove',e=>{const rect=node.getBoundingClientRect();cursor=Math.max(0,Math.min(rows.length-1,Math.round(((e.clientX-rect.left)/rect.width*W-L)/(W-L-R)*(rows.length-1))));hover(cursor)});node.addEventListener('pointerleave',()=>hover(rows.length-1));node.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();cursor=Math.max(0,Math.min(rows.length-1,cursor+(e.key==='ArrowLeft'?-1:1)));hover(cursor)}});
 }
 function hover(i){
  const d=rows[i],day=d.time.slice(0,10);
  if(inspect){
   const points=(markers.get(day)||[]).filter(p=>p.rule_id).map(resonanceText);
   if(!points.length){
    const events=(crossMarkers.get(day)||[]).map(x=>x.label);
    if(events.length)points.push(`${day} ${events.join(' / ')} · 交叉观察`);
   }
   const text=points.join(' / ')||inspect.dataset.default;
   inspect.textContent=text;
   inspect.title=text;
  }
  for(const p of plots){const cross=p.panel.querySelector('.cross');cross.setAttribute('x1',p.x(i));cross.setAttribute('x2',p.x(i));let label=p.panel.querySelector('.plot-head span');label.textContent=p.type==='price'?`${d.time.replace('T',' ').slice(0,period==='intraday'?16:10)}　开 ${fmt(d.open)}　高 ${fmt(d.high)}　低 ${fmt(d.low)}　收 ${fmt(d.close)}`:p.type==='volume'?`${d.volume>=1e8?fmt(d.volume/1e8)+' 亿股':fmt(d.volume/1e4)+' 万股'}`:p.type==='kdj'?`K ${fmt(d.k)}　D ${fmt(d.d)}　J ${fmt(d.j)}`:`快线 ${fmt(d.dif)}　慢线 ${fmt(d.dea)}　柱 ${fmt(d.macd)}`;}}
 hover(rows.length-1);const foot=document.createElement('div');foot.className='chart-dates';const stamp=t=>t.replace('T',' ').slice(0,period==='intraday'?16:10);foot.style.display='flex';foot.style.justifyContent='space-between';foot.innerHTML='<span></span><span></span>';foot.children[0].textContent=stamp(rows[0].time);foot.children[1].textContent=stamp(rows.at(-1).time);root.append(foot);
}
