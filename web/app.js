const DEFAULTS={salary1:60000,salary2:60000,sac1:1000,sac2:450,share2:500,shareMode:'net',loanPlan:'2',price:525000,deposit:15,term:25,spread:.5};
const GBP=new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP',maximumFractionDigits:0});
const pct=v=>Number.isFinite(v)?`${v.toFixed(1)}%`:'—';
const money=v=>Number.isFinite(v)?GBP.format(v):'—';
const el=id=>document.getElementById(id);
let state=null,settings={...DEFAULTS},rateRange='5';
try{const saved=JSON.parse(localStorage.getItem('houselens-settings')||'{}');settings={...settings,...saved};}catch{}

const {netMonthly,householdNet,repayment}=window.HouseMath;
function makeChart(target,series,config={}){
 const mount=el(target); if(!mount)return;
 const all=series.flatMap(s=>s.points.map(p=>p.y)).filter(Number.isFinite);
 if(!all.length){mount.innerHTML=`<div class="chart-empty">${config.empty||'Insufficient observations to draw this chart.'}</div>`;return;}
 const w=710,h=240,pad={l:42,r:13,t:13,b:35}; const values=series.flatMap(s=>s.points.map(p=>p.x));const xmin=Math.min(...values),xmax=Math.max(...values); let lo=Math.min(0,...all),hi=Math.max(0,...all)*1.12;if(lo===hi)hi=lo+1;
 const x=v=>pad.l+(v-xmin)/(xmax-xmin||1)*(w-pad.l-pad.r);
 const y=v=>h-pad.b-(v-lo)/(hi-lo)*(h-pad.t-pad.b);
 let content='';for(let i=0;i<=4;i++){const val=lo+(hi-lo)*i/4;const yy=y(val);content+=`<line x1="${pad.l}" y1="${yy}" x2="${w-pad.r}" y2="${yy}" stroke="#edf1f3"/><text x="${pad.l-8}" y="${yy+4}" text-anchor="end" font-size="11" fill="#95a4b2">${val.toFixed(config.decimals??1)}${config.suffix??''}</text>`;}
 for(const tick of (config.ticks||[])){content+=`<text x="${x(tick.x)}" y="${h-9}" text-anchor="middle" font-size="10" fill="#91a1b0">${tick.label}</text>`;}
 for(const s of series){if(!s.points.length)continue;const points=s.points.filter(p=>Number.isFinite(p.y)).map(p=>`${x(p.x)},${y(p.y)}`).join(' ');if(points)content+=`<polyline points="${points}" fill="none" stroke="${s.color}" stroke-width="${s.width||3}" stroke-linejoin="round" stroke-linecap="round" ${s.dash?'stroke-dasharray="6 5"':''}/>`;}
 mount.innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${config.label||'Trend line chart'}">${content}</svg>`;
}
function setText(id,value){if(el(id))el(id).textContent=value;}
function rates(){if(!state)return [];return state.history||[];}
function freshDate(date,maxAgeDays){const time=Date.parse(date||'');return Number.isFinite(time)&&Date.now()-time<=maxAgeDays*86400000&&Date.now()-time>=-86400000;}
function renderBankChart(){const cutoff=rateRange==='all'?'1900-01-01':new Date(Date.now()-5*365.25*86400000).toISOString().slice(0,10);const observations=rates().filter(p=>p.date>=cutoff).map(p=>({x:Date.parse(p.date),y:+p.rate}));if(!observations.length)return makeChart('rateChart',[],{});const now=Date.parse((state.bankRateAsOf||new Date().toISOString().slice(0,10)));const vals=[...observations];if(now>vals.at(-1).x) vals.push({x:now,y:state.bankRate});const start=vals[0].x,end=vals.at(-1).x;const years=[];for(let year=Math.max(1984,new Date(start).getUTCFullYear()+1);year<=new Date(end).getUTCFullYear();year+=(rateRange==='all'?5:1))years.push({x:Date.UTC(year,0,1),label:String(year)});
 makeChart('rateChart',[{color:'#405c79',points:vals},{color:'#a0d1b6',dash:true,points:vals.map(p=>({x:p.x,y:p.y+Number(settings.spread)}))}],{ticks:years,suffix:'%',label:'Bank Rate and model mortgage rate since 2021'});
}
function getForecast(month){if(!freshDate(state?.ois?.asOf,14))return null;const arr=state?.ois?.forecast||[];if(!arr.length)return null;const exact=arr.find(v=>v.months===month);if(exact)return Number.isFinite(exact.rate)?exact.rate:null;const sorted=[...arr].sort((a,b)=>a.months-b.months),before=[...sorted].reverse().find(p=>p.months<=month),after=sorted.find(p=>p.months>=month);if(!before||!after)return null;return before.months===after.months?before.rate:before.rate+(after.rate-before.rate)*(month-before.months)/(after.months-before.months);}
function marketTrend(){
 const snapshots=(state?.snapshots||[]).filter(s=>Number.isFinite(s.medianPrice)&&s.count>=3).slice(-24);
 if(snapshots.length>=6){
   const first=snapshots[0],last=snapshots.at(-1);
   const days=(Date.parse(last.date)-Date.parse(first.date))/86400000;
   if(days>=35&&first.medianPrice>0){
     const rate=Math.pow(last.medianPrice/first.medianPrice,30.44/days)-1;
     return {monthly:Math.max(-.02,Math.min(.02,rate)),source:'Station-area asking-price snapshots',confidence:'Limited: the mix of homes can change'};
   }
 }
 const h=state?.hpi;
 if(h&&freshDate(h.date+'-01',125)&&Number.isFinite(h.annualChange)&&h.annualChange>-50){
   const rate=Math.pow(1+h.annualChange/100,1/12)-1;
   return {monthly:Math.max(-.02,Math.min(.02,rate)),source:`Basildon HPI (${h.date})`,confidence:'Broad-area, historical trend; not a Billericay prediction'};
 }
 return null;
}
function renderScenarios(){
 const net=householdNet(settings),price=Number(settings.price),dep=Number(settings.deposit),term=Number(settings.term),trend=marketTrend();
 const arr=[0,3,6,12].map(month=>{
   const implied=month===0?(freshDate(state.bankRateAsOf,14)?state.bankRate:null):getForecast(month);
   const targetRate=typeof implied==='number'&&Number.isFinite(implied)?implied+Number(settings.spread):null;
   const targetPrice=month===0?price:trend?price*Math.pow(1+trend.monthly,month):null;
   const payment=targetRate===null||targetPrice===null?null:repayment(targetPrice,dep,targetRate,term);
   return {month,targetRate,targetPrice,payment};
 });
 const todayPayment=arr[0].payment;
 el('scenarioList').innerHTML=arr.map(s=>{const delta=s.payment!==null&&todayPayment!==null?s.payment-todayPayment:null;const comparison=s.month===0?'Current baseline':delta===null?'Not enough data':Math.abs(delta)<1?'About the same':delta<0?`${money(Math.abs(delta))}/mo cheaper`:`${money(delta)}/mo more expensive`;return `<div class="scenario-item"><span>${s.month===0?'Today':`+${s.month} mo`}</span><div><div class="scenario-bar"><b style="width:${s.payment===null?0:Math.max(0,Math.min(100,s.payment/net*200))}%"></b></div><small>${s.month===0?'Observed Bank Rate':s.payment===null?'Missing OIS rate or local-price signal':`Model rate ${s.targetRate.toFixed(2)}%`}</small><small class="scenario-comparison ${delta===null?'':delta<0?'better':delta>0?'worse':''}">${comparison}</small></div><strong>${s.payment===null?'Not yet available':money(s.payment)}${s.payment!==null?`<small>${pct(s.payment/net*100)} of net</small>`:''}</strong></div>`}).join('');
 setText('forecastBasis',trend?`Illustrative house-price path: ${trend.source} (${trend.confidence}). Short-end OIS provides a market-implied rate proxy, not an actual mortgage quote.`:'Forward repayments are withheld until both the short-end OIS curve and a house-price trend are available.');
}
function renderOverview(){if(!state)return;const net=householdNet(settings),rate=state.bankRate+Number(settings.spread),p=repayment(+settings.price,+settings.deposit,rate,+settings.term),share=net>0?p/net*100:0;
 setText('takehome',money(net));setText('mortgageRate',pct(rate));setText('repayment',money(p));setText('mortgageLabel',`${money(+settings.price)} example · ${settings.deposit}% deposit`);setText('affordability',pct(share));setText('affNote',`${money(net-p)} after mortgage`);setText('affDescription',`For a ${money(+settings.price)} property with a ${settings.deposit}% deposit, based on your estimated household take-home.`);
 setText('donutNumber',pct(share));setText('mortgageShare',money(p));setText('remaining',money(net-p));el('donut').style.background=`conic-gradient(#e3a08f 0 ${Math.max(0,Math.min(100,share))}%,#b9e7c7 ${Math.max(0,Math.min(100,share))}% 100%)`;
 setText('criteriaCount',state.listings.length?`${state.listings.length} qualifying matches in collected sample`:'No live properties yet · feed not connected');
 renderBankChart();renderScenarios();renderOutlook();
}
function escapeHtml(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function renderListings(){const age=state.listingsAsOf?(Date.now()-Date.parse(state.listingsAsOf))/86400000:Infinity;const properties=age<60?(state.listings||[]):[],net=householdNet(settings),rate=state.bankRate+Number(settings.spread);
 el('listingsAlert').hidden=properties.length>0;setText('listingSummary',properties.length?`${properties.length} matches in provider sample · observed ${state.listingsAsOf?.slice(0,10)} (not necessarily all available homes)`:'No current qualifying listings in a connected sample yet, or the feed needs refreshing.');
 el('properties').innerHTML=properties.map(p=>{const payment=repayment(p.price,+settings.deposit,rate,+settings.term),safe=typeof p.url==='string'&&/^https:\/\//.test(p.url)?p.url:null;return `<article class="property"><div class="property-top"><div><div class="type">${escapeHtml(p.type)} · ${escapeHtml(p.bedrooms)}+ beds</div><h3>${escapeHtml(p.address||'Address withheld by portal')}</h3></div><span class="chip">${escapeHtml(p.distanceMiles.toFixed(2))} mi</span></div><p>${money(p.price)} asking price · ${escapeHtml(p.portal||'Property feed')}</p><div class="property-stats"><div><small>Model repayment</small><strong>${money(payment)}/mo</strong></div><div><small>Of take-home</small><strong>${pct(payment/net*100)}</strong></div></div>${safe?`<a href="${escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">View original listing ↗</a>`:''}</article>`}).join('');}
function renderOutlook(){const forecast=freshDate(state?.ois?.asOf,14)?(state?.ois?.forecast||[]):[],observations=[{months:0,rate:state.bankRate},...forecast.filter(p=>Number.isFinite(p.rate))];makeChart('oisChart',forecast.length?[{color:'#88bb9f',points:observations.map(p=>({x:p.months,y:p.rate}))}]:[],{empty:'Market-implied forecasts are not yet available. Run the scheduled BoE data updater.',ticks:[{x:0,label:'Now'},{x:3,label:'3 months'},{x:6,label:'6 months'},{x:12,label:'12 months'}],suffix:'%',label:'Short-end OIS forward interest rate path'});
 setText('oisDate',state.ois.asOf?`AS OF ${state.ois.asOf}`:'SONIA OIS');setText('oisNote',forecast.length?'These are short-end OIS instantaneous forwards, not guaranteed future Bank Rate decisions.':'Awaiting the Bank of England yield-curve archive.');setText('breakeven',freshDate(state.gilts.asOf,14)&&Number.isFinite(state.gilts.rpiBreakeven)?pct(state.gilts.rpiBreakeven):'Not available');const guidance=state.guidance;const guidanceAge=guidance?.asOf?(Date.now()-Date.parse(guidance.asOf))/86400000:Infinity;setText('guidanceText',guidance&&guidanceAge<150?`${guidance.headline} (checked ${guidance.asOf}).`:'Fresh BoE guidance unavailable; see the official Monetary Policy Report.');
 const snaps=(state.snapshots||[]).filter(p=>Number.isFinite(p.medianPrice));makeChart('priceChart',snaps.length>1?[{color:'#81bfa4',points:snaps.map(p=>({x:Date.parse(p.date),y:p.medianPrice/1000}))}]:[],{empty:'Waiting for multiple real property-market snapshots. Collecting them twice weekly will reveal the direction of asking prices.',decimals:0,suffix:'k',label:'Median asking price of qualifying properties over recorded snapshots'});
 const trend=marketTrend();setText('trendNote',trend===null?`Recorded snapshots: ${snaps.length}. Awaiting data for a 3/6/12-month price scenario.`:`Price-change scenario: ${(trend.monthly*100).toFixed(2)}% per month · ${trend.source}. ${trend.confidence}. Clipped at ±2%/month to limit extremes.`);
 const h=state?.hpi;renderSourceHealth();setText('hpiNote',h?`Official Basildon local-authority HPI: ${money(h.averagePrice)} average, ${h.annualChange==null?'annual change unavailable':pct(h.annualChange)+' annual change'}, for ${h.date}. This is a broader-area benchmark, not your station radius.`:'Awaiting a valid official HM Land Registry Basildon HPI observation.');
}
function renderSourceHealth(){const items=[['Bank Rate',state?.bankRateAsOf,14, 'Bank of England IADB'],['SONIA forwards',state?.ois?.asOf,14,'Bank of England yield curves'],['Gilt-implied inflation',state?.gilts?.asOf,14,'Bank of England yield curves'],['Local house prices',state?.hpi?.date?state.hpi.date+'-01':null,125,'HM Land Registry (Basildon LA)'],['Qualifying properties',state?.listingsAsOf,60,'Optional licensed PropertyData sample']];el('sourceHealth').innerHTML=items.map(([name,date,age,provider])=>`<div class="source-item"><div><strong>${name}</strong><small>${provider}</small></div><div class="source-status ${freshDate(date,age)?'healthy':'needs-attention'}">${freshDate(date,age)?'Current':'Missing / check date'}<small>${date?escapeHtml(String(date).slice(0,10)):'Not connected'}</small></div></div>`).join('');}
function renderSettings(){for(const [k,v] of Object.entries(settings)){const field=document.querySelector(`[data-setting="${k}"]`);if(field)field.value=v;}const rate=state.bankRate+Number(settings.spread),loan=+settings.price*(1-+settings.deposit/100),p=repayment(+settings.price,+settings.deposit,rate,+settings.term);el('mortgageBreakdown').innerHTML=`House price <strong>${money(+settings.price)}</strong><br>Deposit <strong>${money(+settings.price*settings.deposit/100)}</strong><br>Mortgage balance <strong>${money(loan)}</strong><br>Estimated repayment <strong>${money(p)} / month</strong>`;}
function render(){if(!state)return;const d=state.lastRun?new Date(state.lastRun).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'}):'Not yet scheduled';setText('date-label',`SNAPSHOT · ${d.toUpperCase()}`);setText('freshness',state.lastRun?`Updated ${d}`:'Awaiting live setup');el('freshness').classList.toggle('warning',!state.lastRun||!state.listings.length);el('setupAlert').hidden=!!state.listings.length;setText('dataHealth',state.errors?.length?`${state.errors.length} source warning(s) · check data freshness in the outlook`:'');renderOverview();renderListings();renderSettings();}
async function load(){try{const res=await fetch(`./data/state.json?bust=${Date.now()}`,{cache:'no-store'});if(!res.ok)throw Error(`${res.status}`);state=await res.json();render();}catch(err){setText('freshness','Data unavailable');document.querySelectorAll('.chart').forEach(e=>e.innerHTML='<div class="chart-empty">Could not load the published snapshot. Check your connection.</div>');console.warn(err);}}
function switchTab(name){document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===name));document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('selected',n.dataset.tab===name));location.hash=name;window.scrollTo({top:0,behavior:'instant'});}
document.querySelectorAll('[data-tab]').forEach(n=>n.addEventListener('click',()=>switchTab(n.dataset.tab)));document.querySelectorAll('[data-jump]').forEach(n=>n.addEventListener('click',()=>switchTab(n.dataset.jump)));el('reload').addEventListener('click',load);el('reset').addEventListener('click',()=>{settings={...DEFAULTS};localStorage.setItem('houselens-settings',JSON.stringify(settings));render();});document.querySelectorAll('[data-setting]').forEach(input=>input.addEventListener('change',()=>{let val=input.value;if(input.type==='number')val=Number(val);settings[input.dataset.setting]=val;localStorage.setItem('houselens-settings',JSON.stringify(settings));render();el('saveToast').classList.add('show');setTimeout(()=>el('saveToast').classList.remove('show'),1600);}));
document.querySelectorAll('[data-range]').forEach(button=>button.addEventListener('click',()=>{rateRange=button.dataset.range;document.querySelectorAll('[data-range]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',String(b===button));});renderBankChart();}));
if(['overview','listings','outlook','settings'].includes(location.hash.slice(1)))switchTab(location.hash.slice(1));
load();if('serviceWorker' in navigator&&location.protocol!=='file:')navigator.serviceWorker.register('./sw.js').catch(()=>{});
