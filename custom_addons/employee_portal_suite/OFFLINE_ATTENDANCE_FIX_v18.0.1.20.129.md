# Offline Attendance hotfix - 18.0.1.20.129

- Restored Check In / Check Out buttons to normal HTML submit buttons so online attendance still works if the enhanced JS fails or is stale.
- Enhanced attendance logic now intercepts form submit only after it is loaded.
- Attendance controller is loaded directly from the Attendance template with a versioned static URL to bypass stale Odoo/PWA asset bundles.
- Service-worker cache bumped to v49.
- Offline queue, trusted-device verification, GPS/geofence and sync behavior remain enabled when the controller loads.
