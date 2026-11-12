/* HouseLens station-radius matching and local criteria, also testable in Node.
   NEVER bundle an API key with this file or commit one to GitHub. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.HouseListings = api;
})(typeof window !== 'undefined' ? window : undefined, function () {
  'use strict';
  const STATION = {lat: 51.62889045, lng: 0.418635763};
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
  const REASON_LABELS = Object.freeze({
    invalid:'Malformed provider record',currency:'Non-GBP price',price:'Asking price not available',
    bedrooms:'Bedrooms not specified',status:'Not available for sale',otherType:'Excluded property type',
    outside:'Outside broad station radius',id:'Missing listing ID',
    unconfirmedType:'Property type not confirmed',location:'Location not verified'
  });
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
  // API requests run only in the scheduled GitHub workflow; no credentials
  // are ever sent from the public GitHub Pages site.
  return {STATION,DEFAULT_FILTERS,REASON_LABELS,finiteNum,haversine,validateFilters,classify,sortMatches};
});
