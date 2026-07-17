const CACHE = "meteoro-portal-v3";
const ASSETS = [
  "/portal/",
  "/portal/styles.css",
  "/portal/operations.css",
  "/portal/modules.css",
  "/portal/reports.css",
  "/portal/app.js",
  "/portal/manifest.webmanifest",
  "/portal/vendor/leaflet/leaflet.css",
  "/portal/vendor/leaflet/leaflet.js",
  "/portal/vendor/leaflet-heat.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // Tolerante a arquivo ausente (ex.: vendor ainda não baixado).
      Promise.allSettled(ASSETS.map((asset) => cache.add(asset)))
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

async function stampAndStore(request, response) {
  const body = await response.clone().blob();
  const headers = new Headers(response.headers);
  headers.set("X-Meteoro-Cached-At", new Date().toISOString());
  const stamped = new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
  const cache = await caches.open(CACHE);
  await cache.put(request, stamped);
}

// Estratégia network-first:
// - /portal/*: online entrega fresco; offline cai para o cache do shell.
// - GET /api/v1/public/*: online entrega fresco e guarda cópia carimbada;
//   offline devolve a cópia com X-Meteoro-Cached-At (o portal exibe a idade).
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  const isPortal = url.pathname.startsWith("/portal");
  const isPublicApi = url.pathname.startsWith("/api/v1/public");
  if (!isPortal && !isPublicApi) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          if (isPublicApi) {
            stampAndStore(event.request, response);
          } else {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          }
        }
        return response;
      })
      .catch(async () => {
        const hit = await caches.match(event.request);
        if (hit) return hit;
        throw new TypeError("offline sem cache disponível");
      })
  );
});
