// Guarda fotos y sonidos en el movil: la app va rapida y funciona sin internet.
const V = "olivia-v2";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())
));
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET" || req.headers.has("range")) return;
  const u = new URL(req.url);
  if (u.origin !== location.origin) return;
  if (u.pathname.includes("/img/") || u.pathname.includes("/sounds/")){
    e.respondWith(caches.open(V).then(async c => {
      const hit = await c.match(req); if (hit) return hit;
      const r = await fetch(req); if (r.ok) c.put(req, r.clone()); return r;
    }));
  } else {
    e.respondWith(fetch(req).then(r => { const cl = r.clone(); caches.open(V).then(c => c.put(req, cl)); return r; }).catch(() => caches.match(req)));
  }
});
