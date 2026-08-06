/** @odoo-module **/

/**
 * Web Push opt-in for Employee Portal Suite.
 *
 * Shows a small "Enable notifications" pill (see #ep-push-banner in the
 * portal layout) the first time a portal user visits, and silently
 * re-subscribes on later visits if permission was already granted.
 */

(function () {
    'use strict';

    function urlBase64ToUint8Array(base64String) {
        var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
        var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        var rawData = window.atob(base64);
        var outputArray = new Uint8Array(rawData.length);
        for (var i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    function callJsonRpc(url, params) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: params || {}, id: Date.now() }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) { return data.result; });
    }

    function getVapidPublicKey() {
        return fetch('/employee_portal_suite/push/vapid_public_key')
            .then(function (r) { return r.json(); })
            .then(function (data) { return data.publicKey; });
    }

    function setBannerVisible(visible) {
        var banner = document.getElementById('ep-push-banner');
        if (banner) {
            banner.style.display = visible ? 'flex' : 'none';
        }
    }

    function subscribeUser() {
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            return Promise.resolve(false);
        }
        return navigator.serviceWorker.register('/push-sw.js', { scope: '/' }).then(function (registration) {
            return getVapidPublicKey().then(function (publicKey) {
                if (!publicKey) {
                    return false;
                }
                return registration.pushManager
                    .subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(publicKey),
                    })
                    .then(function (subscription) {
                        return callJsonRpc('/employee_portal_suite/push/subscribe', {
                            subscription: subscription.toJSON(),
                        });
                    });
            });
        });
    }

    function enableNotifications() {
        if (!('Notification' in window)) {
            return;
        }
        Notification.requestPermission().then(function (permission) {
            if (permission === 'granted') {
                subscribeUser().then(function () { setBannerVisible(false); });
            } else {
                setBannerVisible(false);
            }
        });
    }
    window.epEnablePushNotifications = enableNotifications;

    function dismissBanner() {
        setBannerVisible(false);
        try {
            window.localStorage.setItem('ep_push_banner_dismissed', '1');
        } catch (e) { /* ignore storage errors (private mode, etc.) */ }
    }
    window.epDismissPushBanner = dismissBanner;

    document.addEventListener('DOMContentLoaded', function () {
        if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
            return;
        }

        if (Notification.permission === 'granted') {
            // Already allowed: make sure the subscription is (still) registered,
            // no banner needed.
            subscribeUser();
            return;
        }

        if (Notification.permission === 'denied') {
            return;
        }

        var dismissed = false;
        try {
            dismissed = window.localStorage.getItem('ep_push_banner_dismissed') === '1';
        } catch (e) { /* ignore */ }

        if (!dismissed) {
            setBannerVisible(true);
        }
    });
})();
