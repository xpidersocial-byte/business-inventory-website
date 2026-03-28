/**
 * FBIHM Service Worker v4.9 (High-Reliability Offline Mode)
 */

const CACHE_NAME = 'fbihm-v4.9';
const OFFLINE_URL = '/offline';

// Core assets that MUST be available
const ASSETS_TO_CACHE = [
    '/',
    '/login',
    OFFLINE_URL,
    '/static/manifest.json',
    '/favicon.ico',
    '/static/js/offline-manager.js',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css'
];

// Navigation routes we want to work offline if visited once
const NAV_ROUTES = ['/dashboard', '/items', '/sales', '/sales-summary', '/pos', '/bulletin'];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then(async (cache) => {
            console.log('[SW] Precaching system assets');
            for (const url of ASSETS_TO_CACHE) {
                try {
                    // Use 'follow' to handle redirects during precache
                    await cache.add(new Request(url, { redirect: 'follow' }));
                } catch (e) {
                    console.warn(`[SW] Skip precache for: ${url}`);
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

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);

    // Skip dynamic system routes
    if (url.pathname.includes('socket.io') || url.pathname.startsWith('/health')) return;

    // STRATEGY: Network-First for Navigation
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).then((networkResponse) => {
                // If successful, save a copy to the cache
                if (networkResponse && networkResponse.status === 200) {
                    const cacheCopy = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                }
                return networkResponse;
            }).catch(() => {
                // If network fails, try the cache for this specific page
                return caches.match(event.request).then((cachedResponse) => {
                    // If not in cache, show the generic Offline Page
                    return cachedResponse || caches.match(OFFLINE_URL);
                });
            })
        );
        return;
    }

    // STRATEGY: Stale-While-Revalidate for Assets (Images, CSS, JS)
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            const fetchPromise = fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const cacheCopy = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                }
                return networkResponse;
            }).catch(() => cachedResponse);

            return cachedResponse || fetchPromise;
        })
    );
});
