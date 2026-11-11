# EPS 18.0.1.20.128 - Offline Attendance reliability fix

- Does not rely only on navigator.onLine for attendance actions.
- Online attendance POST is performed with fetch; real network failure automatically queues the same attendance event offline.
- GPS captured for the attempted online action is reused for the offline event on network failure.
- Service worker cache version bumped to v48.
- Attendance asks the service worker to cache Employee Portal + Attendance and relevant loaded assets.
- Service worker acknowledges cache preparation through MessageChannel.
- UI shows "Preparing Offline..." until cache confirmation and "Offline Ready" only after confirmation.
- Service worker scope normalized to /my/employee/.
- Trusted-device functionality from 18.0.1.20.127 is preserved.
