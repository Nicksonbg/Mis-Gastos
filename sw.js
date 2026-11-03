// Guarda la app para que funcione sin internet
const CACHE='mis-gastos-v24';
const FILES=['./','index.html','manifest.webmanifest','icon-180.png','icon-192.png','icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES)));self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));self.clients.claim()});
// Primero la red (para recibir actualizaciones); si no hay conexión, la copia guardada
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;
  const u=new URL(e.request.url);if(u.origin!==location.origin&&!u.href.startsWith('https://www.gstatic.com/firebasejs/'))return;
  e.respondWith(Promise.race([fetch(e.request,{cache:'reload'}),new Promise((_,rj)=>setTimeout(()=>rj(new Error('slow')),4000))]).then(r=>{const cp=r.clone();caches.open(CACHE).then(c=>c.put(e.request,cp));return r}).catch(()=>caches.match(e.request).then(r=>r||caches.match('index.html'))))});
