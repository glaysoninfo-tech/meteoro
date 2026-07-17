const CACHE = "meteoro-portal-v2";
const ASSETS = ["/portal/", "/portal/styles.css", "/portal/app.js", "/portal/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

// Network-first com fallback ao cache: online sempre entrega a versão fresca;
// offline mantém o portal funcional com a última versão válida em cache.
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET" || !event.request.url.includes("/portal/")) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
