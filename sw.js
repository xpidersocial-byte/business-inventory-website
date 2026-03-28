/**
 * FBIHM Service Worker v6.0 (Ultra Offline-First)
 * Handles precaching, background sync, and UI notifications.
 */

const CACHE_NAME = 'fbihm-v6.0';
const OFFLINE_URL = '/offline';
const SYNC_CHANNEL = new BroadcastChannel('offline_sync_status');

// Core assets for the "App Shell"
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
 * Background Sync Implementation
 */
self.addEventListener('sync', (event) => {
    if (event.tag === 'fbihm-sync') {
        console.log('[SW] Background Sync Triggered');
        // The actual sync logic is in offline-manager.js, but the SW 
        // keeps the process alive and can trigger a BroadcastChannel message.
        SYNC_CHANNEL.postMessage({ type: 'SYNC_STARTED' });
    }
});

/**
 * Fetch interception with Network-First strategy for pages
 */
self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);
    if (url.pathname.includes('socket.io') || url.pathname.startsWith('/health')) return;

    // Navigation (HTML Pages)
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request)
                .then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const cacheCopy = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                    }
                    return networkResponse;
                })
                .catch(() => {
                    return caches.match(event.request).then((cached) => cached || caches.match(OFFLINE_URL));
                })
        );
        return;
    }

    // Static Assets (Cache-First)
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) return cachedResponse;
            return fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const cacheCopy = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                }
                return networkResponse;
            });
        })
    );
});
