/**
 * FBIHM Service Worker v11.0 (Enterprise Offline-First)
 * Features: Absolute Cache-First for assets, optimized data layer, and DNS resilience.
 */

const CACHE_NAME = 'fbihm-v11.0';
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
            console.log('[SW v11] Hydrating Application Shell');
            for (const url of ASSETS_TO_CACHE) {
                try {
                    await cache.add(new Request(url, { redirect: 'follow' }));
                } catch (e) { console.warn(`[SW v11] Precache Skip: ${url}`); }
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

/**
 * Enterprise Fetch Strategy
 * 1. Cache-First for static assets (instant load)
 * 2. Stale-While-Revalidate for core pages
 */
self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    
    const url = new URL(event.request.url);
    if (url.pathname.includes('socket.io') || url.pathname.startsWith('/health')) return;

    // Is it a static asset (CSS, JS, Image)? -> Absolute Cache-First
    const isAsset = url.pathname.match(/\.(js|css|png|jpg|jpeg|webp|svg|woff2|mp3)$/) || 
                    url.host.includes('cdn.jsdelivr.net');

    if (isAsset) {
        event.respondWith(
            caches.match(event.request).then(cached => {
                return cached || fetch(event.request).then(res => {
                    if (res.ok) {
                        const copy = res.clone();
                        caches.open(CACHE_NAME).then(c => c.put(event.request, copy));
                    }
                    return res;
                });
            })
        );
        return;
    }

    // Navigation and API -> Stale-While-Revalidate
    event.respondWith(
        caches.match(event.request).then(cached => {
            const fetchPromise = fetch(event.request).then(networkRes => {
                if (networkRes.ok) {
                    const copy = networkRes.clone();
                    caches.open(CACHE_NAME).then(c => c.put(event.request, copy));
                }
                return networkRes;
            }).catch(() => null);

            return cached || fetchPromise || new Response('', { status: 503 });
        })
    );
});

self.addEventListener('sync', (event) => {
    if (event.tag === 'fbihm-sync') {
        const SYNC_CHANNEL = new BroadcastChannel('offline_sync_status');
        SYNC_CHANNEL.postMessage({ type: 'SYNC_STARTED' });
    }
});
