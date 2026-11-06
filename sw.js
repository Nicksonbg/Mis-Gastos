// Guarda la app para que funcione sin internet
const CACHE='mis-gastos-v67';
const FILES=['./','index.html','manifest.webmanifest','icon-180.png','icon-192.png','icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES)));self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));self.clients.claim()});
// Primero la red (para recibir actualizaciones); si no hay conexión, la copia guardada
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;
  const u=new URL(e.request.url);if(u.origin!==location.origin&&!u.href.startsWith('https://www.gstatic.com/firebasejs/'))return;
  e.respondWith(Promise.race([fetch(e.request,{cache:'reload'}),new Promise((_,rj)=>setTimeout(()=>rj(new Error('slow')),4000))]).then(r=>{const cp=r.clone();caches.open(CACHE).then(c=>c.put(e.request,cp));return r}).catch(()=>caches.match(e.request).then(r=>r||caches.match('index.html'))))});
// Notificaciones de pagos (recordatorio el día antes)
self.addEventListener('push',e=>{let d={};try{d=e.data.json()}catch(x){d={title:'Personal Balance',body:e.data?e.data.text():''}}
  e.waitUntil(self.registration.showNotification(d.title||'Personal Balance',{body:d.body||'',tag:d.tag||'pb',icon:'icon-192.png',badge:'icon-192.png',data:{url:d.url||'./'}}))});
self.addEventListener('notificationclick',e=>{e.notification.close();
  e.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(cs=>{for(const c of cs){if('focus' in c)return c.focus()}return clients.openWindow(e.notification.data&&e.notification.data.url||'./')}))});
