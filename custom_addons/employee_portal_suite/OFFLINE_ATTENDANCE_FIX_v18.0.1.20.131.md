Employee Portal Suite 18.0.1.20.131 - Offline Attendance reliability fix

- Removed attendance_offline.js from web.assets_frontend to prevent stale/duplicate bundled copies from blocking the versioned Attendance-page controller.
- Attendance page now loads attendance_offline.js only once, directly with ?v=131.
- Attendance controller directly registers the Employee Portal service worker.
- Attendance page and required same-origin assets are cached directly from the page using Cache Storage.
- Service worker cache bumped to employee-portal-pwa-v50.
- Offline Ready is only shown after the Attendance HTML and attendance controller are confirmed in cache.
- Trusted-device server-side enrollment/enforcement from 18.0.1.20.130 is unchanged.
