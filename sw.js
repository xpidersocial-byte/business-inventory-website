/**
 * FBIHM Service Worker v6.1 (Fail-Safe Offline Mode)
 * Ensures no "Stuck in Loading" by implementing global timeouts and error catches.
 */

const CACHE_NAME = 'fbihm-v6.1';
const OFFLINE_URL = '/offline';
const SYNC_CHANNEL = new BroadcastChannel('offline_sync_status');

const ASSETS_TO_CACHE = [
    '/',
    '/login',
    '/dashboard',
    '/items',
    '/sales',
    '/sales-summary',
    '/pos',
    '/bulletin',
    OFFLINE_URL,
    '/static/manifest.json',
    '/favicon.ico',
    '/static/sounds/notification.mp3',
    '/static/js/offline-manager.js',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    'https://cdn.socket.io/4.5.4/socket.io.min.js',
    'https://cdn.jsdelivr.net/npm/sweetalert2@11',
    'https://cdn.jsdelivr.net/npm/chart.js'
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then(async (cache) => {
            console.log('[SW] Precaching App Shell');
            for (const url of ASSETS_TO_CACHE) {
                try {
                    await cache.add(new Request(url, { redirect: 'follow' }));
                } catch (e) {
                    console.warn(`[SW] Precache failed: ${url}`);
                }
            }
        })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) return caches.delete(cacheName);
                })
            );
        })
    );
});

/**
 * Robust Fetch with Timeout
 */
async function fetchWithTimeout(request, timeout = 3000) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);
    try {
        const response = await fetch(request, { signal: controller.signal });
        clearTimeout(id);
        return response;
    } catch (err) {
        clearTimeout(id);
        throw err;
    }
}

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);
    if (url.pathname.includes('socket.io') || url.pathname.startsWith('/health')) return;

    // STRATEGY: Navigation (HTML Pages)
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetchWithTimeout(event.request, 4000)
                .then((networkResponse) => {
                    if (networkResponse.status === 200) {
                        const cacheCopy = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                    }
                    return networkResponse;
                })
                .catch(() => {
                    // Fail to cache or offline page
                    return caches.match(event.request).then((cached) => cached || caches.match(OFFLINE_URL));
                })
        );
        return;
    }

    // STRATEGY: Static Assets & API (Cache-First with Fail-Safe)
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) return cachedResponse;

            return fetch(event.request)
                .then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const cacheCopy = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                    }
                    return networkResponse;
                })
                .catch((err) => {
                    // CRITICAL FIX: Return a null response or local placeholder instead of crashing
                    console.log(`[SW] Fetch failed for ${url.pathname}, device likely offline.`);
                    if (event.request.destination === 'image') {
                        // Optionally return a tiny transparent pixel or placeholder
                        return new Response('', { status: 404, statusText: 'Offline' });
                    }
                    return null; // Let the browser handle the missing resource gracefully
                });
        })
    );
});

self.addEventListener('sync', (event) => {
    if (event.tag === 'fbihm-sync') {
        SYNC_CHANNEL.postMessage({ type: 'SYNC_STARTED' });
    }
});
