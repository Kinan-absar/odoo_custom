const CACHE_NAME = 'absar-chat-static-v2';
const STATIC_ASSETS = [
  '/chat/manifest.webmanifest',
  '/absar_chat_pwa/static/icons/icon-192.png',
  '/absar_chat_pwa/static/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('Absar Chat SW cache failed:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // CRITICAL: Never cache authenticated HTML, API routes, longpolling or websocket
  if (
    url.pathname.startsWith('/chat/api') ||
    url.pathname.startsWith('/web/dataset') ||
    url.pathname.startsWith('/longpolling') ||
    url.pathname.startsWith('/websocket') ||
    event.request.mode === 'navigate' ||
    url.pathname === '/chat' ||
    url.pathname === '/chat/'
  ) {
    return;
  }

  // Cache-first for static icons and manifest only
  if (
    url.pathname.startsWith('/absar_chat_pwa/static/') ||
    url.pathname === '/chat/manifest.webmanifest'
  ) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        return (
          cached ||
          fetch(event.request).then((response) => {
            if (response && response.status === 200) {
              const clone = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            }
            return response;
          })
        );
      })
    );
  }
});
