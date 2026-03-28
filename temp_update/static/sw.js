// FBIHM Service Worker v5.0 (Resilient & Offline-First)
const CACHE_NAME = 'xpider-v5.0';
const OFFLINE_URL = '/offline';

// Priority assets: App Shell, must be cached for the app to even start
const MANDATORY_ASSETS = [
    '/',
    '/login',
    OFFLINE_URL,
    '/static/favicon.ico',
    '/static/js/offline-manager.js',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css'
];

// Optional assets: Will be cached if possible, but won't block installation
const OPTIONAL_ASSETS = [
    '/static/images/login_hero.webp',
    'https://cdn.jsdelivr.net/npm/sweetalert2@11/dist/sweetalert2.min.css',
    'https://cdn.jsdelivr.net/npm/sweetalert2@11'
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then(async (cache) => {
            console.log('[SW] Pre-caching mandatory assets...');
            // Mandatory assets must pass
            await cache.addAll(MANDATORY_ASSETS);
            
            // Optional assets can fail individually
            console.log('[SW] Pre-caching optional assets...');
            return Promise.allSettled(
                OPTIONAL_ASSETS.map(url => cache.add(url).catch(err => console.error('[SW] Failed optional cache:', url, err)))
            );
        })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        Promise.all([
            // Claim all clients instantly
            self.clients.claim(),
            // Cleanup old caches
            caches.keys().then((cacheNames) => {
                return Promise.all(
                    cacheNames.map((cacheName) => {
                        if (cacheName !== CACHE_NAME) {
                            console.log('[SW] Deleting old cache:', cacheName);
                            return caches.delete(cacheName);
                        }
                    })
                );
            })
        ])
    );
});

self.addEventListener('fetch', (event) => {
    // Only handle GET requests from http/https
    if (event.request.method !== 'GET' || !event.request.url.startsWith('http')) return;

    // 1. Navigation (HTML): Network-First with Offline Fallback
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(async () => {
                const cache = await caches.open(CACHE_NAME);
                const offline = await cache.match(OFFLINE_URL);
                if (offline) return offline;
                
                const root = await cache.match('/');
                if (root) return root;

                return new Response('System is offline. No cached version available.', {
                    status: 503,
                    statusText: 'Service Unavailable',
                    headers: { 'Content-Type': 'text/html' }
                });
            })
        );
        return;
    }

    // 2. Static Assets: Cache-First then Network (Stale-While-Revalidate)
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) {
                // Background update
                fetch(event.request).then(async (networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const cache = await caches.open(CACHE_NAME);
                        cache.put(event.request, networkResponse.clone());
                    }
                }).catch(() => {});
                return cachedResponse;
            }

            // Not in cache, try network
            return fetch(event.request).then(async (networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const cache = await caches.open(CACHE_NAME);
                    cache.put(event.request, networkResponse.clone());
                }
                return networkResponse;
            }).catch(() => {
                // Offline fallback for assets
                if (event.request.destination === 'image') {
                    return caches.match('/static/favicon.ico');
                }
                return new Response('Offline resource unavailable.', { status: 404, statusText: 'Offline' });
            });
        })
    );
});

// PUSH NOTIFICATIONS
self.addEventListener('push', (event) => {
    let data = { title: 'Notification', body: 'New update from system.' };
    if (event.data) {
        try { data = event.data.json(); } catch (e) { data.body = event.data.text(); }
    }
    const options = {
        body: data.body,
        icon: '/static/images/login_hero.webp',
        badge: '/static/images/login_hero.webp',
        vibrate: [100, 50, 100],
        tag: 'fbihm-push'
    };
    event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
            if (clients.length > 0) return clients[0].focus();
            return self.clients.openWindow('/');
        })
    );
});
