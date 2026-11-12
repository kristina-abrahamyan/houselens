/* HouseLens free listings adapter and local criteria, also testable in Node.
   NEVER bundle an API key with this file or commit one to GitHub. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.HouseListings = api;
})(typeof window !== 'undefined' ? window : undefined, function () {
  'use strict';
  const STATION = {lat: 51.62889045, lng: 0.418635763};
  const SEARCH = 'https://api.untera.io/api/v1/listings/search';
  const TYPES = ['Detached', 'Semi-detached', 'End of terrace'];
  const DEFAULT_FILTERS = Object.freeze({minPrice:450000,maxPrice:600000,minBeds:3,maxMiles:.75,
    detached:true,semi:true,endTerrace:true});

  function finiteNum(v) {
    if(typeof v === 'string') v = v.replace(/[£,$\s]/g,'');
    const n = Number(v);
    return (v !== '' && v !== null && v !== undefined && Number.isFinite(n)) ? n : null;
  }
  function haversine(lat,lng) {
    const a=STATION.lat*Math.PI/180,b=STATION.lng*Math.PI/180,c=lat*Math.PI/180,d=lng*Math.PI/180;
    const v=Math.sin((c-a)/2)**2+Math.cos(a)*Math.cos(c)*Math.sin((d-b)/2)**2;
    return 3958.7613*2*Math.asin(Math.min(1,Math.sqrt(Math.max(0,v))));
  }
  function coordsOf(raw) {
    const nested=[raw.coordinates,raw.geo,raw.location].find(x=>x && typeof x==='object' && !Array.isArray(x));
    let lat=finiteNum(raw.latitude??raw.lat??nested?.latitude??nested?.lat);
    let lng=finiteNum(raw.longitude??raw.lng??raw.lon??nested?.longitude??nested?.lng??nested?.lon);
    if(Array.isArray(raw.coordinates)&&raw.coordinates.length===2){
      lng=finiteNum(raw.coordinates[0]); lat=finiteNum(raw.coordinates[1]);
    }
    return lat!==null && lng!==null && Math.abs(lat)<=90 && Math.abs(lng)<=180 ? {lat,lng} : null;
  }
  function typeOf(...values) {
    const text=values.filter(x=>typeof x==='string').join(' ').toLowerCase().replace(/[_-]/g,' ');
    if(/\bend\s+(?:of\s+)?terrace(?:d)?\b/.test(text) || /\bendterrace\b/.test(text) || /\bterrace\s+end\b/.test(text)) return 'End of terrace';
    if(/\bsemi\s*detached\b/.test(text)) return 'Semi-detached';
    if(/\bdetached\b/.test(text)) return 'Detached';
    return null;
  }
  // A rejection reason is recorded BEFORE we discard a provider record.
  // No addresses or API keys are included in the diagnostic counts.
  const REASON_LABELS = Object.freeze({
    invalid:'Invalid provider record',currency:'No original GBP asking price',
    price:'No usable asking price',bedrooms:'Bedrooms not specified',
    status:'Not clearly available for sale',otherType:'Definitely not an allowed house type',
    outside:'Outside the broad Billericay station area',
    location:'Billericay location cannot be established',id:'Missing listing identifier',
    unconfirmedType:'Property type not confirmed'
  });
  function normalizeDetailed(raw) {
    if(!raw || typeof raw!=='object')return {item:null,reason:'invalid'};
    // Never treat provider-normalised USD figures as a GBP asking price.
    if(String(raw.original_currency||'').toUpperCase()!=='GBP')return {item:null,reason:'currency'};
    const price=finiteNum(raw.original_price), beds=finiteNum(raw.bedrooms??raw.beds);
    if(price===null||price<=0)return {item:null,reason:'price'};
    if(beds===null||beds<1)return {item:null,reason:'bedrooms'};
    const status=[raw.status,raw.availability,raw.transaction].filter(Boolean).join(' ').toLowerCase();
    if(/\bsold\b|\bsstc\b|under.offer|\brent(?:al)?\b|\blet\b/.test(status))return {item:null,reason:'status'};
    const c=coordsOf(raw),dist=c?haversine(c.lat,c.lng):null;
    if(dist!==null&&dist>3.5)return {item:null,reason:'outside'};
    const address=String(raw.address||raw.location_name||(typeof raw.location==='string'?raw.location:'')||raw.city||raw.title||'Address not provided').slice(0,180);
    if(dist===null&&!/billericay|cm12/i.test(address))return {item:null,reason:'location'};
    const kind=typeOf(raw.property_type,raw.type,raw.title);
    if(!kind){
      const text=[raw.property_type,raw.type,raw.title].filter(x=>typeof x==='string').join(' ').toLowerCase();
      // These are explicitly excluded, not "maybe detached" properties.
      if(/\bflat\b|\bapartment\b|\bmaisonette\b|\bstudio\b|\bbungalow\b|\bland\b|\bplot\b|\bcommercial\b|\bmid[ -]?terrace\b/.test(text))
        return {item:null,reason:'otherType'};
    }
    const url=typeof raw.url==='string'&&raw.url.startsWith('https://')?raw.url:'';
    const id=String(raw.id??raw._id??url??'').slice(0,160);
    if(!id)return {item:null,reason:'id'};
    const item={id,price:Math.round(price),bedrooms:Math.trunc(beds),type:kind||'Type unverified',address,
      distanceMiles:dist===null?null:Math.round(dist*1000)/1000,distanceVerified:dist!==null,
      url,portal:'Untera',sourceProvider:'Untera'};
    return {item,reason:kind?null:'unconfirmedType'};
  }
  function normalizeItem(raw) { return normalizeDetailed(raw).item; }
  function parseResponse(body,diagnostics) {
    if(!body || !Array.isArray(body.results) || body.success===false)throw new Error('Provider returned an invalid listings response');
    return body.results.map(raw=>{
      const {item,reason}=normalizeDetailed(raw);
      if(diagnostics){diagnostics.rawResults++;if(reason)diagnostics.reasons[reason]=(diagnostics.reasons[reason]||0)+1;}
      return item;
    }).filter(Boolean);
  }
  function validateFilters(p) {
    const minPrice=finiteNum(p.minPrice),maxPrice=finiteNum(p.maxPrice),minBeds=finiteNum(p.minBeds),maxMiles=finiteNum(p.maxMiles);
    if(minPrice===null||maxPrice===null||minPrice<0||maxPrice<minPrice||maxPrice>10000000)throw new Error('Enter a valid minimum and maximum asking price.');
    if(minBeds===null||minBeds<1||minBeds>20||!Number.isInteger(minBeds))throw new Error('Bedrooms must be between 1 and 20.');
    if(maxMiles===null||maxMiles<.1||maxMiles>3)throw new Error('Station distance must be between 0.1 and 3 miles.');
    if(!p.detached&&!p.semi&&!p.endTerrace)throw new Error('Select at least one house type.');
    return {minPrice,maxPrice,minBeds,maxMiles,detached:!!p.detached,semi:!!p.semi,endTerrace:!!p.endTerrace};
  }
  function classify(item,filters) {
    if(!item || !Number.isFinite(item.price) || !Number.isFinite(item.bedrooms))return 'excluded';
    if(item.price<filters.minPrice||item.price>filters.maxPrice||item.bedrooms<filters.minBeds)return 'excluded';
    if((item.type==='Detached'&&!filters.detached)||(item.type==='Semi-detached'&&!filters.semi)||(item.type==='End of terrace'&&!filters.endTerrace))return 'excluded';
    if(item.type==='Type unverified')return !Number.isFinite(item.distanceMiles)||item.distanceMiles<=filters.maxMiles ? 'unverified' : 'excluded';
    if(!TYPES.includes(item.type))return 'excluded';
    if(!Number.isFinite(item.distanceMiles))return 'unverified';
    return item.distanceMiles<=filters.maxMiles ? 'verified' : 'excluded';
  }
  function sortMatches(items,filters) {
    const verified=[],unverified=[];
    for(const item of items||[]){const where=classify(item,filters);if(where==='verified')verified.push(item);if(where==='unverified')unverified.push(item);}
    verified.sort((a,b)=>a.distanceMiles-b.distanceMiles||a.price-b.price);
    unverified.sort((a,b)=>a.price-b.price);
    return {verified,unverified};
  }
  async function searchFresh(apiKey,{fetchImpl, maxPages=8}={}) {
    if(!/^unt_[A-Za-z0-9_-]+$/.test(String(apiKey).trim()))throw new Error('Enter your free Untera API key (starting with unt_).');
    const call=fetchImpl||fetch;
    const listings=[],seen=new Set();let pages=0, truncated=false;
    const diagnostics={rawResults:0,reasons:{}};
    for(let page=1;page<=maxPages;page++){
      // Fetch a broad Billericay inventory and apply ALL numeric / distance
      // filters locally. Never confuse USD price filters with GBP budgets.
      const query=new URLSearchParams({country:'GB',location:'Billericay',transaction:'sale',pageSize:'50',page:String(page)});
      const response=await call(`${SEARCH}?${query}`,{headers:{'X-API-Key':apiKey.trim(),'Accept':'application/json'},cache:'no-store'});
      if(!response.ok)throw new Error(response.status===401||response.status===403?'API key rejected by Untera.':`Listing service returned HTTP ${response.status}.`);
      const body=await response.json();
      const normalized=parseResponse(body,diagnostics);
      for(const item of normalized)if(!seen.has(item.id)){listings.push(item);seen.add(item.id);}
      pages=page;
      if(body.results.length<50 && body.hasMore!==true && !body.next_page)break;
      if(body.results.length===0)break;
      if(page===maxPages)truncated=true;
    }
    return {listings,pages,truncated,diagnostics,at:new Date().toISOString()};
  }
  return {STATION,DEFAULT_FILTERS,REASON_LABELS,finiteNum,haversine,typeOf,coordsOf,normalizeItem,normalizeDetailed,parseResponse,validateFilters,classify,sortMatches,searchFresh};
});
