const DEFAULTS={salary1:60000,salary2:60000,sac1:1000,sac2:450,share2:500,shareMode:'net',loanPlan:'2',price:525000,deposit:15,term:25,spread:.5};
const GBP=new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP',maximumFractionDigits:0});
const pct=v=>Number.isFinite(v)?`${v.toFixed(1)}%`:'—';
const money=v=>Number.isFinite(v)?GBP.format(v):'—';
const el=id=>document.getElementById(id);
let state=null,settings={...DEFAULTS},rateRange='5';
const listingLib=window.HouseListings;
let propertyFilters={...listingLib.DEFAULT_FILTERS};
try{localStorage.removeItem('houselens-untera-key');const f=JSON.parse(localStorage.getItem('houselens-property-filters')||'null');if(f)propertyFilters=listingLib.validateFilters(f);}catch{}


try{const saved=JSON.parse(localStorage.getItem('houselens-settings')||'{}');settings={...settings,...saved};}catch{}

const {netMonthly,householdNet,repayment,chartBounds,paymentInTodayMoney}=window.HouseMath;
function makeChart(target,series,config={}){
 const mount=el(target); if(!mount)return;
 const all=series.flatMap(s=>s.points.map(p=>p.y)).filter(Number.isFinite);
 if(!all.length){mount.innerHTML=`<div class="chart-empty">${config.empty||'Insufficient observations to draw this chart.'}</div>`;return;}
 const w=710,h=240,pad={l:42,r:13,t:13,b:35}; const values=series.flatMap(s=>s.points.map(p=>p.x));const xmin=Math.min(...values),xmax=Math.max(...values); const {lo,hi}=chartBounds(all,config);
 const x=v=>pad.l+(v-xmin)/(xmax-xmin||1)*(w-pad.l-pad.r);
 const y=v=>h-pad.b-(v-lo)/(hi-lo)*(h-pad.t-pad.b);
 let content='';for(let i=0;i<=4;i++){const val=lo+(hi-lo)*i/4;const yy=y(val);content+=`<line x1="${pad.l}" y1="${yy}" x2="${w-pad.r}" y2="${yy}" stroke="#edf1f3"/><text x="${pad.l-8}" y="${yy+4}" text-anchor="end" font-size="11" fill="#95a4b2">${val.toFixed(config.decimals??1)}${config.suffix??''}</text>`;}
 for(const tick of (config.ticks||[])){content+=`<text x="${x(tick.x)}" y="${h-9}" text-anchor="middle" font-size="10" fill="#91a1b0">${tick.label}</text>`;}
 for(const s of series){if(!s.points.length)continue;const valid=s.points.filter(p=>Number.isFinite(p.y));const points=valid.map(p=>`${x(p.x)},${y(p.y)}`).join(' ');if(points)content+=`<polyline points="${points}" fill="none" stroke="${s.color}" stroke-width="${s.width||3}" stroke-linejoin="round" stroke-linecap="round" ${s.dash?'stroke-dasharray="6 5"':''}/>`;
   if(config.showValues)valid.forEach((p,i)=>{const xx=x(p.x),yy=y(p.y);const label=`${config.valuePrefix||''}${p.y.toFixed(config.valueDecimals??0)}${config.suffix||''}`;const anchor=i===0?'start':i===valid.length-1?'end':'middle';const offset=i===0?7:i===valid.length-1?-7:0;content+=`<circle cx="${xx}" cy="${yy}" r="4.5" fill="${s.color}" stroke="white" stroke-width="2"/><text x="${xx+offset}" y="${yy-12}" text-anchor="${anchor}" font-size="12" font-weight="700" fill="#365f54">${label}</text>`;});
 }
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
 const sold=state?.localSales;
 if(sold&&freshDate(sold.asOf,75)&&Number.isFinite(sold.annualChange)
    && sold.count>=12&&sold.previousCount>=12){
   const monthly=Math.pow(1+sold.annualChange/100,1/12)-1;
   return {monthly:Math.max(-.02,Math.min(.02,monthly)),
           source:`${sold.scope} completed sales (through ${sold.periodEnd})`,
           confidence:'Illustrative historical year-on-year medians; sales mix and registration delays matter. Not the 0.75-mile station radius or a prediction'};
 }
 const h=state?.hpi;
 if(h&&freshDate(h.date+'-01',125)&&Number.isFinite(h.annualChange)&&h.annualChange>-50){
   const rate=Math.pow(1+h.annualChange/100,1/12)-1;
   return {monthly:Math.max(-.02,Math.min(.02,rate)),source:`Basildon HPI (${h.date})`,confidence:'Broad-area, historical trend; not a Billericay prediction'};
 }
 return null;
}
function calculateScenarios(){
 const price=Number(settings.price),dep=Number(settings.deposit),term=Number(settings.term),trend=marketTrend();
 const arr=[0,3,6,12].map(month=>{
   const implied=month===0?(freshDate(state.bankRateAsOf,14)?state.bankRate:null):getForecast(month);
   const targetRate=typeof implied==='number'&&Number.isFinite(implied)?implied+Number(settings.spread):null;
   const targetPrice=month===0?price:trend?price*Math.pow(1+trend.monthly,month):null;
   const payment=targetRate===null||targetPrice===null?null:repayment(targetPrice,dep,targetRate,term);
   return {month,targetRate,targetPrice,payment};
 });
 return {arr,trend};
}
function renderScenarios(){
 const net=householdNet(settings),price=Number(settings.price);
 const {arr,trend}=calculateScenarios();
 const todayPayment=arr[0].payment;
 el('scenarioList').innerHTML=arr.map(s=>{const delta=s.payment!==null&&todayPayment!==null?s.payment-todayPayment:null;const comparison=s.month===0?'Current baseline':delta===null?'Not enough data':Math.abs(delta)<1?'About the same':delta<0?`${money(Math.abs(delta))}/mo cheaper`:`${money(delta)}/mo more expensive`;const houseScenario=s.month&&s.targetPrice!==null?`Illustrative house price ${money(s.targetPrice)} (${(100*(s.targetPrice/price-1)>=0?'+':'')}${(100*(s.targetPrice/price-1)).toFixed(1)}%)`:'';return `<div class="scenario-item"><span>${s.month===0?'Today':`+${s.month} mo`}</span><div><div class="scenario-bar"><b style="width:${s.payment===null?0:Math.max(0,Math.min(100,s.payment/net*200))}%"></b></div><small>${s.month===0?'Observed Bank Rate':s.payment===null?'Missing OIS rate or local-price signal':`Model rate ${s.targetRate.toFixed(2)}%`}</small>${houseScenario?`<small>${houseScenario}</small>`:''}<small class="scenario-comparison ${delta===null?'':delta<0?'better':delta>0?'worse':''}">${comparison}</small></div><strong>${s.payment===null?'Not yet available':money(s.payment)}${s.payment!==null?`<small>${pct(s.payment/net*100)} of net</small>`:''}</strong></div>`}).join('');
 setText('forecastBasis',trend?`Illustrative, not a prediction: ${trend.source}. ${trend.confidence}. Assumes the same deposit percentage, mortgage term and household net income throughout. Rates are OIS-derived proxies + your spread, not lender offers. Stamp duty, fees and upkeep are excluded.`:'Forward repayments are withheld until both the short-end OIS curve and a house-price trend are available.');
}
function renderOverview(){if(!state)return;const net=householdNet(settings),rate=state.bankRate+Number(settings.spread),p=repayment(+settings.price,+settings.deposit,rate,+settings.term),share=net>0?p/net*100:0;
 setText('takehome',money(net));setText('mortgageRate',pct(rate));setText('repayment',money(p));setText('mortgageLabel',`${money(+settings.price)} example · ${settings.deposit}% deposit`);setText('affordability',pct(share));setText('affNote',`${money(net-p)} after mortgage`);setText('affDescription',`For a ${money(+settings.price)} property with a ${settings.deposit}% deposit, based on your estimated household take-home.`);
 setText('donutNumber',pct(share));setText('mortgageShare',money(p));setText('remaining',money(net-p));el('donut').style.background=`conic-gradient(#e3a08f 0 ${Math.max(0,Math.min(100,share))}%,#b9e7c7 ${Math.max(0,Math.min(100,share))}% 100%)`;
 
 renderBankChart();renderScenarios();renderOutlook();
}
function escapeHtml(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function currentListingFeed(){
 const provider=String(state?.listingProvider||'');
 const isRealty=/^RealtyAPI\b/i.test(provider);
 const outcome=state?.listingRefresh?.status || (!isRealty?'legacy':'unknown');
 const isSuccess=isRealty && !['failed','missing_key'].includes(outcome);
 const at=isSuccess?state?.listingsAsOf:null;
 const age=at?(Date.now()-Date.parse(at))/86400000:Infinity;
 const recent=Number.isFinite(age)&&age>=0&&age<=7;
 return {listings:recent?(state?.listings||[]):[],at,
   origin:'Scheduled RealtyAPI snapshot',pages:isSuccess?state?.listingCoverage?.pages:null,
   truncated:isSuccess&&!!state?.listingCoverage?.truncated,
   stale:!!at&&!recent,
   status:outcome,
   detail:state?.listingRefresh?.message||'No RealtyAPI search recorded yet.',
   diagnostics:isSuccess?state?.listingCoverage?.diagnostics:null};
}
function filterSummary(){const f=propertyFilters;return `${money(f.minPrice)}–${money(f.maxPrice)} · ${f.minBeds}+ beds · within ${f.maxMiles} miles`}
function listingCard(p,unverified,net,rate){
 const payment=repayment(p.price,+settings.deposit,rate,+settings.term);
 const typeUnverified=p.type==='Type unverified';const missingDistance=!Number.isFinite(p.distanceMiles);
 const issues=[typeUnverified?'Type not confirmed':null,missingDistance?'Distance unverified':null].filter(Boolean);
 const safe=typeof p.url==='string'&&/^https:\/\/[^\s"<>]+$/.test(p.url)?p.url:null;
 return `<article class="property"><div class="property-top"><div><div class="type">${escapeHtml(p.type)} · ${escapeHtml(p.bedrooms)} beds</div><h3>${escapeHtml(p.address||'Address not provided')}</h3></div><span class="chip ${unverified?'unverified-chip':''}">${issues.length?issues.join(' · '):`${p.distanceMiles.toFixed(2)} mi`}</span></div><p>${money(p.price)} asking price</p><div class="property-stats"><div><small>Model repayment</small><strong>${money(payment)}/mo</strong></div><div><small>Of take-home pay</small><strong>${pct(payment/net*100)}</strong></div></div>${unverified?'<p class="property-footnote">Needs independent confirmation of house type and/or station distance; not a confirmed match.</p>':''}${safe?`<a href="${escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">View original listing ↗</a>`:''}</article>`;
}
function renderListings(){
 const feed=currentListingFeed(),net=householdNet(settings),rate=state.bankRate+Number(settings.spread),results=listingLib.sortMatches(feed.listings,propertyFilters);
 const hasFeed=!!feed.at&&!feed.stale;el('listingsAlert').hidden=hasFeed;
 if(!hasFeed){
   const title=el('listingsAlert').querySelector('strong'),note=el('listingsAlert').querySelector('span');
   const missing=feed.status==='missing_key', failed=feed.status==='failed', legacy=feed.status==='legacy';
   if(title)title.textContent=feed.stale?'RealtyAPI listings expired.':missing?'RealtyAPI key not configured.':failed?'RealtyAPI request failed.':legacy?'Awaiting first RealtyAPI snapshot.':'No current RealtyAPI listings.';
   if(note)note.textContent=feed.stale?'Last RealtyAPI snapshot is over seven days old. Check the latest GitHub workflow.':missing?'Add REALTYAPI_KEY to GitHub Actions secrets and rerun the workflow.':failed?'See the Update from authoritative sources step in GitHub Actions for the error.':legacy?'The published data still contains the old provider snapshot; rerun the new v1.7 workflow after updating main.':feed.detail;
 }
 const searched=feed.listings.length;
 const diag=feed.diagnostics;
 const detail=el('listingDiagnostics');
 if(diag&&Number.isFinite(diag.rawResults)){
   const ranked=Object.entries(diag.reasons||{}).sort((a,b)=>b[1]-a[1]).slice(0,4);
   const explanation=ranked.length?ranked.map(([reason,count])=>`${count} ${listingLib.REASON_LABELS[reason]||reason}`).join(' · '):'No excluded or unconfirmed records in the sample.';
   detail.textContent=`Provider returned ${diag.rawResults} raw records. HouseLens retained ${searched} potential listings for review. ${explanation}. Counts describe the downloaded sample, not all homes on the market. ${feed.truncated?`The ${feed.pages}-page limit was reached.`:''}`;
   detail.hidden=false;
 }else detail.hidden=true;
 const coverage=feed.status==='legacy'?'The downloaded snapshot is still from the previous Untera integration.':(state?.listingCoverage?.note||feed.detail||'This is an incomplete third-party listing sample; some houses may be absent.');
 setText('listingDate',feed.at?`${feed.origin.toUpperCase()} · ${feed.at.slice(0,10)}`:'PROPERTY FEED');
 setText('listingSummary',`${results.verified.length} confirmed within radius · ${results.unverified.length} possible needing verification · ${searched} potential listings in ${feed.origin.toLowerCase()}. ${filterSummary()}. ${feed.truncated?'Search limited to '+feed.pages+' pages. ':''}${feed.stale?'Scheduled results expired. ':''}${coverage}`);
 el('properties').innerHTML=results.verified.length?results.verified.map(p=>listingCard(p,false,net,rate)).join(''):'<div class="chart-empty property-empty">No verified matches in this feed for these filters. That does not mean there are no homes on the market.</div>';
 el('unverifiedBlock').hidden=!results.unverified.length;
 el('unverifiedProperties').innerHTML=results.unverified.map(p=>listingCard(p,true,net,rate)).join('');
 el('attribution').hidden=!hasFeed;
 const f=propertyFilters;
 const inputs={filterMinPrice:f.minPrice,filterMaxPrice:f.maxPrice,filterBeds:f.minBeds,filterMiles:f.maxMiles};
 for(const [id,value] of Object.entries(inputs)){if(document.activeElement!==el(id))el(id).value=value;}
 el('filterDetached').checked=f.detached;el('filterSemi').checked=f.semi;el('filterEndTerrace').checked=f.endTerrace;
 setText('criteriaDistance',`Within ${f.maxMiles} miles`);
 setText('criteriaBudget',`${money(f.minPrice)}–${money(f.maxPrice)}`);
 setText('criteriaBeds',`${f.minBeds}+ bedrooms`);
 setText('criteriaCount',hasFeed?`${results.verified.length} verified matches · ${results.unverified.length} need checks`:'No live listings connected yet · change filters in Properties');el('providerCredit').hidden=!hasFeed;
}
function readFilters(){return listingLib.validateFilters({minPrice:el('filterMinPrice').value,maxPrice:el('filterMaxPrice').value,minBeds:el('filterBeds').value,maxMiles:el('filterMiles').value,detached:el('filterDetached').checked,semi:el('filterSemi').checked,endTerrace:el('filterEndTerrace').checked});}
function saveFilters(){
 try{propertyFilters=readFilters();localStorage.setItem('houselens-property-filters',JSON.stringify(propertyFilters));setText('filterMessage','Filters applied. Search results have been recalculated from the latest available listings.');el('filterMessage').className='field-note success';renderListings();}
 catch(err){setText('filterMessage',err.message);el('filterMessage').className='field-note error';}
}
function renderOutlook(){const forecast=freshDate(state?.ois?.asOf,14)?(state?.ois?.forecast||[]):[],observations=[{months:0,rate:state.bankRate},...forecast.filter(p=>Number.isFinite(p.rate))];makeChart('oisChart',forecast.length?[{color:'#88bb9f',points:observations.map(p=>({x:p.months,y:p.rate}))}]:[],{empty:'Market-implied forecasts are not yet available. Run the scheduled BoE data updater.',ticks:[{x:0,label:'Now'},{x:3,label:'3 months'},{x:6,label:'6 months'},{x:12,label:'12 months'}],suffix:'%',label:'Short-end OIS forward interest rate path'});
 setText('oisDate',state.ois.asOf?`AS OF ${state.ois.asOf}`:'SONIA OIS');setText('oisNote',forecast.length?'These are short-end OIS instantaneous forwards, not guaranteed future Bank Rate decisions.':'Awaiting the Bank of England yield-curve archive.');
 const gilt=state?.gilts, inflationRef=gilt?.inflationReference || (Number.isFinite(gilt?.rpiBreakeven)?{months:12,rate:gilt.rpiBreakeven}:null);
 const validInflation=freshDate(gilt?.asOf,14)&&Number.isFinite(inflationRef?.rate);
 setText('breakeven',validInflation?pct(inflationRef.rate):'Not available');
 setText('breakevenLabel',validInflation?`Gilt-implied RPI proxy (${inflationRef.months/12}-year)`:'Gilt-implied RPI proxy (unavailable)');
 setText('inflationCaveat',validInflation?'The figure is an RPI-linked market breakeven for the stated tenor, not a forecast of household inflation or CPI. Longer-dated rates do not predict inflation over the next 3–12 months.':'The importer has not recovered a validated usable inflation maturity. We are leaving this blank rather than substituting an invented forecast.');
 // CPI forecasts are reported as annual inflation rates at specific
 // quarter-ends, NOT precise cumulative predictions over 3, 6 or 12 months.
 const report=state?.cpiProjection;
 const usable=report&&freshDate(report.asOf,160)&&Array.isArray(report.series)&&report.series.length>=2;
 const future=usable?report.series.filter(point=>/20\d{2} Q[1-4]/.test(point.quarter)&&Number.isFinite(point.rate)):[];
 // The report table contains Q4 annual rates, not a 3/6/12-month
 // CPI curve. For a labelled constant-rate illustration only, use the
 // report quarter closest to 12 months from today (within nine months).
 const oneYearFromToday=Date.now()+365.25*86400000;
 const withinRange=future.map(point=>{const m=point.quarter.match(/^(20\d{2}) Q([1-4])$/);return m?{point,date:Date.UTC(+m[1],+m[2]*3,0),gap:Infinity}:null;}).filter(Boolean)
   .map(p=>({...p,gap:Math.abs(p.date-oneYearFromToday)})).sort((a,b)=>a.gap-b.gap);
 const cpiPoint=withinRange.length&&withinRange[0].gap<=275*86400000?withinRange[0].point:null;
 setText('cpiLabel',cpiPoint?`BoE CPI · ${cpiPoint.quarter}`:'BoE CPI central projection');
 setText('cpiValue',cpiPoint?pct(cpiPoint.rate):'Not available');
 setText('cpiNote',usable?`Official central projection (${report.asOf}): ${future.map(p=>`${p.quarter}: ${pct(p.rate)}`).join(' · ')}. These are year-on-year inflation rates at quarter-end, not forecasts for every individual month.`:'No validated, recent official Bank of England CPI projection was imported. Real-money scenarios are withheld.');
 const comparison=el('realPaymentComparison');
 const {arr}=calculateScenarios();
 if(cpiPoint&&cpiPoint.rate>-3&&cpiPoint.rate<=20){
  comparison.textContent=`In today's money (illustrative ${pct(cpiPoint.rate)} annual CPI held constant): `+
    arr.filter(p=>p.month>0).map(p=>`+${p.month} months: ${p.payment===null?'not available':money(paymentInTodayMoney(p.payment,cpiPoint.rate,p.month))}/month`).join(' · ')+
    '. These amounts adjust the purchasing power of projected payments only. The main affordability percentages assume unchanged nominal take-home pay; inflation does not reduce the share of income paid to the lender unless earnings change.';
 }else comparison.textContent='Inflation-adjusted monthly comparisons unavailable until an official BoE CPI projection is validated. Nominal mortgage calculations continue separately.';
 const guidance=state.guidance;const guidanceAge=guidance?.asOf?(Date.now()-Date.parse(guidance.asOf))/86400000:Infinity;setText('guidanceText',guidance&&guidanceAge<150?`${guidance.headline} (checked ${guidance.asOf}).`:'Fresh BoE guidance unavailable; see the official Monetary Policy Report.');
 const snaps=(state.snapshots||[]).filter(p=>Number.isFinite(p.medianPrice));makeChart('priceChart',snaps.length>1?[{color:'#81bfa4',points:snaps.map(p=>({x:Date.parse(p.date),y:p.medianPrice/1000}))}]:[],{empty:'Waiting for multiple real property-market snapshots. Collecting them twice weekly will reveal the direction of asking prices.',decimals:0,suffix:'k',label:'Median asking price of qualifying properties over recorded snapshots'});
 const trend=marketTrend();setText('trendNote',trend===null?`Recorded snapshots: ${snaps.length}. Awaiting data for a 3/6/12-month price scenario.`:`Price-change scenario: ${(trend.monthly*100).toFixed(2)}% per month · ${trend.source}. ${trend.confidence}. Clipped at ±2%/month to limit extremes.`);
 renderLocalSales();
 const h=state?.hpi;renderSourceHealth();setText('hpiNote',h?`Official Basildon local-authority HPI: ${money(h.averagePrice)} average, ${h.annualChange==null?'annual change unavailable':pct(h.annualChange)+' annual change'}, for ${h.date}. This is a broader-area benchmark, not your station radius.`:'Awaiting a valid official HM Land Registry Basildon HPI observation.');
}
function renderLocalSales(){
 const sold=state?.localSales;
 if(!sold||!freshDate(sold.asOf,75)){
   makeChart('localSalesChart',[],{empty:'Waiting for official CM12 completed-sale data. The first import can be larger than subsequent refreshes.'});
   setText('localSalesSummary','A local completed-sales comparison is not available yet.');
   setText('localSalesNote','No validated local sold-price comparison yet. This is not a live listings feed.');
   return;
 }
 makeChart('localSalesChart',[{color:'#4f8d77',points:[
    {x:0,y:sold.previousMedianPrice/1000}, {x:1,y:sold.medianPrice/1000}]}],
    {decimals:0,suffix:'k',zeroBaseline:false,showValues:true,valuePrefix:'£',ticks:[{x:0,label:'Same 6 months prior year'},
                                {x:1,label:`6 months to ${sold.periodEnd}`}],
     label:'Official local detached and semi-detached sold-price medians, year-on-year'});
 const difference=sold.medianPrice-sold.previousMedianPrice;setText('localSalesSummary',`Median completed-sale price was ${money(Math.abs(difference))} ${difference<0?'lower':difference>0?'higher':'unchanged'} (${sold.annualChange>=0?'+':''}${sold.annualChange.toFixed(1)}%). Chart vertical scale is zoomed to show a small difference clearly.`);
 setText('localSalesNote',`${sold.scope} · ${sold.typeDescription}. ${money(sold.previousMedianPrice)} → ${money(sold.medianPrice)} (${sold.annualChange>=0?'+':''}${sold.annualChange.toFixed(1)}% year on year). ${sold.previousCount} prior / ${sold.count} recent sales; ${sold.bandSales} recent sales in the £450k–£600k band. ${sold.note}`);
}
function renderSourceHealth(){
 const gilt=state?.gilts, inf=gilt?.inflationReference || (Number.isFinite(gilt?.rpiBreakeven)?{months:12,rate:gilt.rpiBreakeven}:null);
 const items=[
   ['Bank Rate',state?.bankRateAsOf,14,'Bank of England IADB',Number.isFinite(state?.bankRate)],
   ['SONIA forwards',state?.ois?.asOf,14,'Bank of England yield curves',(state?.ois?.forecast||[]).length===3],
   ['Gilt-implied inflation',gilt?.asOf,14,'Bank of England yield curves',Number.isFinite(inf?.rate)],
   ['Official CPI projection',state?.cpiProjection?.asOf,160,'Bank of England Monetary Policy Report',(state?.cpiProjection?.series||[]).length>=2],
   ['CM12 completed sales',state?.localSales?.asOf,75,'HM Land Registry Price Paid Data',Number.isFinite(state?.localSales?.annualChange)],
   ['Broad-area house prices',state?.hpi?.date?state.hpi.date+'-01':null,125,'HM Land Registry (Basildon LA)',Number.isFinite(state?.hpi?.averagePrice)],
   ['Qualifying property listings',currentListingFeed().at,7, 'RealtyAPI · unofficial Rightmove sample',!!currentListingFeed().at&&!currentListingFeed().stale]
 ];
 el('sourceHealth').innerHTML=items.map(([name,date,age,provider,usable])=>{
    const ok=usable&&freshDate(date,age);
    const note=name==='Gilt-implied inflation'&&ok?`${inf.months/12}-year market tenor`:(date?String(date).slice(0,10):'Not connected');
    return `<div class="source-item"><div><strong>${escapeHtml(name)}</strong><small>${escapeHtml(provider)}</small></div><div class="source-status ${ok?'healthy':'needs-attention'}">${ok?'Usable':'Missing / check data'}<small>${escapeHtml(note)}</small></div></div>`;
 }).join('');
}
function renderSettings(){for(const [k,v] of Object.entries(settings)){const field=document.querySelector(`[data-setting="${k}"]`);if(field)field.value=v;}const rate=state.bankRate+Number(settings.spread),loan=+settings.price*(1-+settings.deposit/100),p=repayment(+settings.price,+settings.deposit,rate,+settings.term);el('mortgageBreakdown').innerHTML=`House price <strong>${money(+settings.price)}</strong><br>Deposit <strong>${money(+settings.price*settings.deposit/100)}</strong><br>Mortgage balance <strong>${money(loan)}</strong><br>Estimated repayment <strong>${money(p)} / month</strong>`;}
function render(){if(!state)return;const d=state.lastRun?new Date(state.lastRun).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'}):'Not yet scheduled';setText('date-label',`SNAPSHOT · ${d.toUpperCase()}`);setText('freshness',state.lastRun?`Updated ${d}`:'Awaiting live setup');el('freshness').classList.toggle('warning',!state.lastRun);el('setupAlert').hidden=!!currentListingFeed().at&&!currentListingFeed().stale;setText('dataHealth',state.errors?.length?`${state.errors.length} source warning(s) · check data freshness in the outlook`:'');renderOverview();renderListings();renderSettings();}
async function load(){try{const res=await fetch(`./data/state.json?bust=${Date.now()}`,{cache:'no-store'});if(!res.ok)throw Error(`${res.status}`);state=await res.json();render();}catch(err){setText('freshness','Data unavailable');document.querySelectorAll('.chart').forEach(e=>e.innerHTML='<div class="chart-empty">Could not load the published snapshot. Check your connection.</div>');console.warn(err);}}
function switchTab(name){document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===name));document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('selected',n.dataset.tab===name));location.hash=name;window.scrollTo({top:0,behavior:'instant'});}
document.querySelectorAll('[data-tab]').forEach(n=>n.addEventListener('click',()=>switchTab(n.dataset.tab)));document.querySelectorAll('[data-jump]').forEach(n=>n.addEventListener('click',()=>switchTab(n.dataset.jump)));el('reload').addEventListener('click',load);
el('applyFilters').addEventListener('click',saveFilters);
el('resetFilters').addEventListener('click',()=>{propertyFilters={...listingLib.DEFAULT_FILTERS};localStorage.setItem('houselens-property-filters',JSON.stringify(propertyFilters));el('filterMessage').className='field-note success';setText('filterMessage','Default filters restored.');renderListings();});

el('reset').addEventListener('click',()=>{settings={...DEFAULTS};localStorage.setItem('houselens-settings',JSON.stringify(settings));render();});document.querySelectorAll('[data-setting]').forEach(input=>input.addEventListener('change',()=>{let val=input.value;if(input.type==='number')val=Number(val);settings[input.dataset.setting]=val;localStorage.setItem('houselens-settings',JSON.stringify(settings));render();el('saveToast').classList.add('show');setTimeout(()=>el('saveToast').classList.remove('show'),1600);}));
document.querySelectorAll('[data-range]').forEach(button=>button.addEventListener('click',()=>{rateRange=button.dataset.range;document.querySelectorAll('[data-range]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',String(b===button));});renderBankChart();}));
if(['overview','listings','outlook','settings'].includes(location.hash.slice(1)))switchTab(location.hash.slice(1));
load();if('serviceWorker' in navigator&&location.protocol!=='file:')navigator.serviceWorker.register('./sw.js').catch(()=>{});
