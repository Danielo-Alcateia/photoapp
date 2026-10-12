// Service Worker do PhotoApp - cache do app shell + PWA instalável.
// Estratégia: STALE-WHILE-REVALIDATE no app shell (responde do cache na hora e
// atualiza em segundo plano). Isso mantém o app usável mesmo quando o Render
// free está "dormindo" (cold start lento): a UI abre instantânea do cache e a
// nova versão entra na próxima abertura.
const CACHE = "photoapp-v6";

const APP_SHELL = [
  "./",
  "./index.html",
  "./manifest.json",
  "./css/styles.css",
  "./js/app.js",
  "./js/api.js",
  "./js/brush.js",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/maskable-512.png",
  "https://cdn.tailwindcss.com",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) =>
        Promise.all(
          APP_SHELL.map((url) =>
            cache.add(new Request(url, { cache: "reload" })).catch(() => null)
          )
        )
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Atualiza o cache em segundo plano (revalidate) sem travar a resposta.
function revalidate(request) {
  return fetch(request)
    .then((response) => {
      if (response && (response.ok || response.type === "opaque")) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
      }
      return response;
    })
    .catch(() => null);
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Nunca cachear chamadas de API nem métodos não-GET (precisam do servidor).
  if (url.pathname.startsWith("/api/") || request.method !== "GET") {
    return;
  }

  // Navegação (abrir o app): responde do cache e revalida em segundo plano.
  if (request.mode === "navigate") {
    event.respondWith(
      caches.match("./index.html").then((cached) => {
        const network = revalidate(request);
        return cached || network.then((r) => r || caches.match("./index.html"));
      })
    );
    return;
  }

  // App shell (stale-while-revalidate).
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = revalidate(request);
      return cached || network.then((r) => r || Response.error());
    })
  );
});
