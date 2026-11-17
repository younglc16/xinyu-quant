/* Finite, data-driven motion. No random prices, permanent loops or network calls. */
const preference=matchMedia('(prefers-reduced-motion: reduce)');
let override=null;try{override=localStorage.getItem('xinyu-motion')}catch{}
const seen=new Map();let pageKey='',lastMarkup='';
export const motionEnabled=()=>override!=='off'&&!preference.matches;
function apply(){document.documentElement.dataset.motion=motionEnabled()?'on':'off';for(const e of document.querySelectorAll('[data-action="motion-toggle"]')){e.setAttribute('aria-pressed',String(motionEnabled()));e.textContent=motionEnabled()?'动效 开':'动效 关';e.title=preference.matches?'系统已启用减少动态效果':'切换轻量界面动效'}if(!motionEnabled())for(const a of document.getAnimations())a.cancel()}
export function toggleMotion(){override=motionEnabled()?'off':'on';try{localStorage.setItem('xinyu-motion',override)}catch{}apply()}
function animate(e,frames,options){if(e&&motionEnabled()&&!document.hidden)e.animate(frames,{...options,fill:'none'})}
export function updateMarketBand(root,markup){
 if(lastMarkup!==markup){root.innerHTML=markup;lastMarkup=markup}
 for(const tile of root.querySelectorAll('[data-market-key]')){
  const key=tile.dataset.marketKey,version=tile.dataset.marketVersion,previous=seen.get(key);
  if(!version||version===previous)continue;seen.set(key,version);
  const stroke=tile.querySelector('.market-trace');
  if(stroke){const length=stroke.getTotalLength();animate(stroke,[{strokeDasharray:`${length}`,strokeDashoffset:length},{strokeDasharray:`${length}`,strokeDashoffset:0}],{duration:750,easing:'cubic-bezier(.2,.7,.2,1)'})}
  animate(tile.querySelector('.market-value'),[{opacity:.45,filter:'brightness(1.6)'},{opacity:1,filter:'brightness(1)'}],{duration:480});
 }
 apply();
}
export function animateView(key){if(key===pageKey)return;pageKey=key;animate(document.querySelector('.terminal-plan-body')||document.querySelector('#main'),[{opacity:.5,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:180,easing:'ease-out'});apply()}
preference.addEventListener('change',apply);
document.addEventListener('visibilitychange',()=>{if(document.hidden)for(const a of document.getAnimations())a.cancel()});
