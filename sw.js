/**
 * FBIHM Service Worker v10.0 (Ultra-Fast App Shell)
 * Implements Stale-While-Revalidate for ALL navigation and assets.
 */

const CACHE_NAME = 'fbihm-v10.0';
const OFFLINE_URL = '/offline';

const ASSETS_TO_CACHE = [
    '/', '/login', '/dashboard', '/items', '/sales', '/sales-summary', '/pos', '/bulletin', '/restock',
    OFFLINE_URL,
    '/static/manifest.json',
    '/favicon.ico',
    '/static/sounds/notification.mp3',
    '/static/js/offline-manager.js',
    'https://cdn.jsdelivr.net/npm/pouchdb@8.0.1/dist/pouchdb.min.js',
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
            for (const url of ASSETS_TO_CACHE) {
                try {
                    await cache.add(new Request(url, { redirect: 'follow' }));
                } catch (e) { console.warn('[SW] Precache Failed:', url); }
            }
        })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
    event.waitUntil(
        caches.keys().then((keys) => Promise.all(keys.map(k => k !== CACHE_NAME && caches.delete(k))))
    );
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    
    const url = new URL(event.request.url);
    if (url.pathname.includes('socket.io') || url.pathname.startsWith('/health')) return;

    // STRATEGY: Stale-While-Revalidate for everything (including Navigation)
    // This makes page transitions instant.
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            const fetchPromise = fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const cacheCopy = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                }
                return networkResponse;
            }).catch(() => {
                // If network fails and no cache, show offline page for navigation
                if (event.request.mode === 'navigate' && !cachedResponse) {
                    return caches.match(OFFLINE_URL);
                }
                return cachedResponse;
            });

            return cachedResponse || fetchPromise;
        })
    );
});

self.addEventListener('sync', (event) => {
    if (event.tag === 'fbihm-sync') {
        const SYNC_CHANNEL = new BroadcastChannel('offline_sync_status');
        SYNC_CHANNEL.postMessage({ type: 'SYNC_STARTED' });
    }
});
