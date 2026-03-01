// XPIDER Service Worker v2.5 (SUPER STRICT FILTERING)
const CACHE_NAME = 'xpider-v2.5';
const ASSETS = [
    '/static/manifest.json',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css'
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS);
        })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        Promise.all([
            clients.claim(),
            // Clear old caches
            caches.keys().then((cacheNames) => {
                return Promise.all(cacheNames.map(c => caches.delete(c)));
            }),
            // Force clear existing notifications
            self.registration.getNotifications().then(notifications => {
                notifications.forEach(n => n.close());
            })
        ])
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    // Ignore navigation and specific routes
    if (event.request.mode === 'navigate' || 
        url.pathname.startsWith('/login') || 
        url.pathname.startsWith('/system-info') || 
        url.pathname.startsWith('/latest-log') ||
        url.pathname.startsWith('/log-client-error') ||
        url.pathname.startsWith('/socket.io')) {
        return;
    }
    event.respondWith(
        caches.match(event.request).then((response) => {
            return response || fetch(event.request).catch(() => null);
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

    // --- SUPER STRICT FILTER ---
    const title = (data.title || '').toUpperCase();
    const body = (data.body || '').toUpperCase();
    
    // Completely ignore anything related to subscriptions
    if (title.includes('SUBSCRIBE') || body.includes('SUBSCRIBE')) {
        console.log('[SW] Blocked subscription spam:', title);
        return;
    }

    const options = {
        body: data.body,
        icon: '/static/images/login_hero.webp',
        badge: '/static/images/login_hero.webp',
        vibrate: [200, 100, 200],
        tag: 'xpider-activity',
        renotify: true
    };

    // Add 3-second delay to match UI
    event.waitUntil(
        new Promise(resolve => setTimeout(resolve, 3000)).then(() => {
            return self.registration.showNotification(data.title, options);
        })
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
