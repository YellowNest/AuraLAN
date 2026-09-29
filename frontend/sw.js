/*
 * Recovery worker for the pre-release development build.
 *
 * A previous worker cached un-hashed assets while the API contract changed.
 * It could therefore keep an iPhone on an incompatible app shell. This worker
 * performs one network-only activation, clears AuraLAN caches, reloads clients,
 * and unregisters itself. PWA offline caching can return once hashed builds exist.
 */
self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith('auralan-')).map((key) => caches.delete(key)));
    await self.clients.claim();
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    await Promise.all(windows.map((client) => client.navigate(client.url)));
    await self.registration.unregister();
  })());
});

self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
