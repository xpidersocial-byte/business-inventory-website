/**
 * FBIHM Service Worker v4.1 (Universal Offline Mode)
 * Implements Stale-While-Revalidate for ALL pages and assets.
 */

const CACHE_NAME = 'fbihm-v4.1';
const OFFLINE_URL = '/offline';

// Core assets to precache during 'install' phase
const ASSETS_TO_CACHE = [
    '/',
    '/login',
    '/dashboard',
    '/inventory/items',
    '/pos', '/sales/summary',
    OFFLINE_URL,
    '/static/manifest.json',
    '/favicon.ico',
    '/static/sounds/notification.mp3',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css',
    '/static/js/offline-manager.js'
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW] Precaching universal assets');
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);

    // Skip dynamic routes that should never be cached
    if (url.pathname.startsWith('/logout') || 
        url.pathname.includes('socket.io') ||
        url.pathname.startsWith('/system-info') ||
        url.pathname.startsWith('/health')) {
        return;
    }

    // Network-First strategy for Navigation to ensure fresh data when online,
    // but fallback to cache or Offline Page when offline.
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const cacheCopy = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                }
                return networkResponse;
            }).catch(() => {
                return caches.match(event.request).then((cachedResponse) => {
                    return cachedResponse || caches.match(OFFLINE_URL);
                });
            })
        );
        return;
    }

    // Stale-While-Revalidate for everything else (CSS, JS, Images, API)
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            const fetchPromise = fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const cacheCopy = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                }
                return networkResponse;
            }).catch(() => {
                return cachedResponse;
            });

            return cachedResponse || fetchPromise;
        })
    );
});

// LISTEN FOR PUSH
self.addEventListener('push', (event) => {
    let data = { title: 'System Alert', body: 'New activity recorded.' };
    if (event.data) {
        try { data = event.data.json(); } catch (e) { data.body = event.data.text(); }
    }
    const options = {
        body: data.body,
        icon: '/static/images/login_hero.webp',
        badge: '/static/images/login_hero.webp',
        vibrate: [200, 100, 200],
        tag: 'xpider-activity',
        renotify: true
    };
    event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
            if (windowClients.length > 0) return windowClients[0].focus();
            return clients.openWindow('/');
        })
    );
});