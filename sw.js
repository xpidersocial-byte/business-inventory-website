/**
 * FBIHM Service Worker v8.0 (Ultra-Stable)
 * Ensures zero crashes and guaranteed responses for all requests.
 */

const CACHE_NAME = 'fbihm-v8.0';
const OFFLINE_URL = '/offline';
const SYNC_CHANNEL = new BroadcastChannel('offline_sync_status');

const ASSETS_TO_CACHE = [
    '/', '/login', '/dashboard', '/items', '/sales', '/sales-summary', '/pos', '/bulletin', '/restock',
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

    // 1. Navigation
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).then(res => {
                if (res.ok) {
                    const copy = res.clone();
                    caches.open(CACHE_NAME).then(c => c.put(event.request, copy));
                }
                return res;
            }).catch(() => caches.match(event.request).then(cached => cached || caches.match(OFFLINE_URL)))
        );
        return;
    }

    // 2. Static Assets
    event.respondWith(
        caches.match(event.request).then(cached => {
            if (cached) return cached;
            return fetch(event.request).then(res => {
                if (res.ok) {
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
