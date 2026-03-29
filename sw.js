/**
* FBIHM Service Worker v9.0 (PouchDB-Ready)
 * Optimized for performance with Stale-While-Revalidate API caching.
 */

const CACHE_NAME = 'fbihm-v9.0';
const OFFLINE_URL = '/offline';
const SYNC_CHANNEL = new BroadcastChannel('offline_sync_status');

const ASSETS_TO_CACHE = [
    '/', '/login', '/dashboard', '/items', '/sales', '/sales-summary', '/pos', '/bulletin', '/restock',
    OFFLINE_URL,
    '/static/manifest.json',
    '/favicon.ico',
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

// Helper to ensure we ALWAYS return a valid Response object
function offlineResponse(status = 503) {
    return new Response('', { status: status, statusText: 'Offline' });
}

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);
    if (url.pathname.includes('socket.io') || url.pathname.startsWith('/health')) return;

    // 1. API Synchronization Cache (Stale-While-Revalidate)
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            caches.open(CACHE_NAME).then(async (cache) => {
                const cachedRes = await cache.match(event.request);
                const fetchPromise = fetch(event.request).then((networkRes) => {
                    // Only cache full responses, not partial 206 responses.
                    if (networkRes.status === 200) {
                        cache.put(event.request, networkRes.clone());
                    }
                    return networkRes;
                }).catch(() => offlineResponse());
                return cachedRes || fetchPromise;
            })
        );
        return;
    }

    // 2. Navigation
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).then(res => {
                // Only cache full responses, not partial 206 responses.
                if (res.status === 200) {
                    const copy = res.clone();
                    caches.open(CACHE_NAME).then(c => c.put(event.request, copy));
                }
                return res;
            }).catch(() => {
                return caches.match(event.request).then(cached => {
                    if (cached) return cached;
                    return caches.match(OFFLINE_URL).then(offlinePage => offlinePage || offlineResponse());
                });
            })
        );
        return;
    }

    // 3. Static Assets (Cache-First)
    event.respondWith(
        caches.match(event.request).then(cached => {
            if (cached) return cached;
            return fetch(event.request).then(res => {
                // Only cache full responses, not partial 206 responses.
                if (res.status === 200) {
                    const copy = res.clone();
                    caches.open(CACHE_NAME).then(c => c.put(event.request, copy));
                }
                return res;
            }).catch(() => offlineResponse());
        })
    );
});

self.addEventListener('sync', (event) => {
    if (event.tag === 'fbihm-sync') {
        SYNC_CHANNEL.postMessage({ type: 'SYNC_STARTED' });
    }
});
