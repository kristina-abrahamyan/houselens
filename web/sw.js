const CACHE='houselens-shell-v8';
const SHELL=['./','./index.html','./styles.css','./app.js','./calculations.js','./listingFilters.js','./manifest.webmanifest','./icons/icon.svg'];
self.addEventListener('install',ev=>ev.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',ev=>ev.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',ev=>{
  if(ev.request.method!=='GET')return;
  const u=new URL(ev.request.url);
  if(u.pathname.endsWith('/data/state.json')) {ev.respondWith(fetch(ev.request,{cache:'no-store'}));return;}
  if(u.origin!==location.origin)return;
  ev.respondWith(fetch(ev.request).then(res=>{const copy=res.clone();caches.open(CACHE).then(c=>c.put(ev.request,copy));return res;}).catch(()=>caches.match(ev.request)));
});
