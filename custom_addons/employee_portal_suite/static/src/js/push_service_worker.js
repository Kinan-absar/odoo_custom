/* Employee Portal Suite — Web Push service worker.
 * Served dynamically from /push-sw.js (root scope) by portal_push.py so it
 * can control the whole site, as required by the Push API.
 */

self.addEventListener('push', function (event) {
    var payload = { title: 'Notification', body: '', url: '/my/employee', tag: 'employee-portal-suite' };
    if (event.data) {
        try {
            payload = Object.assign(payload, event.data.json());
        } catch (e) {
            payload.body = event.data.text();
        }
    }

    var options = {
        body: payload.body,
        tag: payload.tag,
        data: { url: payload.url },
        icon: '/employee_portal_suite/static/description/icon.png',
        badge: '/employee_portal_suite/static/description/icon.png',
    };

    event.waitUntil(self.registration.showNotification(payload.title, options));
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    var url = (event.notification.data && event.notification.data.url) || '/my/employee';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (windowClients) {
            for (var i = 0; i < windowClients.length; i++) {
                var client = windowClients[i];
                if (client.url.indexOf(url) !== -1 && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(url);
            }
        })
    );
});
