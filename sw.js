// Guarda fotos y sonidos en el movil para que la app funcione sin internet.
const V = "olivia-v1";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET" || req.headers.has("range")) return;
  const u = new URL(req.url);
  const isMedia = (u.origin === location.origin && u.pathname.includes("/sounds/")) || u.hostname.includes("inaturalist-open-data") || u.hostname === "static.inaturalist.org";
  if (isMedia){
    e.respondWith(caches.open(V).then(async c => {
      const hit = await c.match(req); if (hit) return hit;
      const r = await fetch(req); if (r.ok || r.type === "opaque") c.put(req, r.clone()); return r;
    }));
  } else if (u.origin === location.origin){
    e.respondWith(fetch(req).then(r => { const cl = r.clone(); caches.open(V).then(c => c.put(req, cl)); return r; }).catch(() => caches.match(req)));
  }
});
