/**
 * FBIHM Service Worker v4.0 (Offline-First Viewer Mode)
 * Implements Stale-While-Revalidate for core pages and data.
 */

const CACHE_NAME = 'fbihm-v4.0';
const OFFLINE_URL = '/offline';

// Core assets to precache during 'install' phase
const ASSETS_TO_CACHE = [
    '/',
    '/login',
    OFFLINE_URL,
    '/static/manifest.json',
    '/favicon.ico',
    '/static/sounds/notification.mp3',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css'
];

self.addEventListener('install', (event) => {
    // Force the waiting service worker to become active immediately
    self.skipWaiting();
    
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW] Precaching key assets for Offline-First mode');
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
});

self.addEventListener('activate', (event) => {
    // Take control of all pages immediately
    event.waitUntil(clients.claim());
    
    // Clear old caches
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[SW] Clearing old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

self.addEventListener('fetch', (event) => {
    // Only intercept GET requests
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);

    // Skip dynamic routes that should never be cached
    if (url.pathname.startsWith('/logout') || 
        url.pathname.includes('socket.io') ||
        url.pathname.startsWith('/system-info') ||
        url.pathname.startsWith('/health')) {
        return;
    }

    // 1. Navigation Requests (HTML Pages)
    if (event.request.mode === 'navigate') {
        event.respondWith(
            caches.match(event.request).then((cachedResponse) => {
                const fetchPromise = fetch(event.request).then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const cacheCopy = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                    }
                    return networkResponse;
                }).catch(() => {
                    return cachedResponse || caches.match(OFFLINE_URL);
                });

                return cachedResponse || fetchPromise;
            })
        );
        return;
    }

    // 2. Static Assets & Local Data API
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            const fetchPromise = fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const cacheCopy = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cacheCopy));
                }
                return networkResponse;
            }).catch(() => {
                // If both fail, return an empty response or an error instead of null
                return new Response('', { status: 404, statusText: 'Not Found' });
            });

            return cachedResponse || fetchPromise;
        })
    );
});

// LISTEN FOR PUSH FROM SERVER
self.addEventListener('push', (event) => {
    let data = { title: 'System Alert', body: 'New activity recorded.' };
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data.body = event.data.text();
        }
    }

    const options = {
        body: data.body,
        icon: '/static/images/login_hero.webp',
        badge: '/static/images/login_hero.webp',
        vibrate: [200, 100, 200],
        tag: 'xpider-activity',
        renotify: true
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
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
