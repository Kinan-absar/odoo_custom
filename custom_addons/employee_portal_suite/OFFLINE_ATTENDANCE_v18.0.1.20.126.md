# Employee Portal Suite 18.0.1.20.126 - Offline Attendance PWA

## Added
- Attendance page can remain usable without network after the employee has logged in online and opened the PWA/Attendance page at least once.
- Service worker caches only the Employee Portal home, Attendance page, and loaded static assets required by those pages.
- Offline Check In / Check Out events are queued on the device with a unique event ID and device UTC timestamp.
- If project geofencing is enforced, offline Check In still requires GPS coordinates. Offline Check Out remains non-blocking and is flagged when location is unavailable/outside the allowed geofence, matching the existing online policy.
- Queued events synchronize in order when the page is online again. A check-in followed by check-out while fully offline becomes one normal Odoo attendance record using the captured device times.
- Duplicate sync is prevented by persisted offline event IDs.
- Attendance records show audit fields for whether check-in/check-out was captured offline and when it synchronized.

## Important behavior
- A new/cleared/logged-out device still needs internet to authenticate. This does not implement offline Odoo login.
- If the PWA remains open, sync starts on the browser `online` event. If it was closed, sync starts the next time Attendance is opened online.
- The normal online attendance POST flow remains unchanged.
- Offline timestamps older than 7 days or more than 5 minutes in the future are rejected for review rather than silently accepted.
- Failed queued events remain on the device and the Attendance page shows that sync attention is needed.

## Files changed
- `__manifest__.py`
- `controllers/portal_attendance.py`
- `controllers/portal_native_discuss.py`
- `models/hr_attendance.py`
- `views/employee_portal_attendance.xml`
- `views/hr_attendance_views.xml`
- new: `static/src/js/attendance_offline.js`

## Local validation performed
- Python compilation passed.
- All 68 XML files parsed successfully.
- New attendance JavaScript passed Node syntax check.
- Generated service-worker JavaScript passed Node syntax check.
- Manifest paths were checked; no referenced data files are missing.

No live Odoo registry, browser PWA installation, real GPS acquisition, or offline/online synchronization against an Odoo database was executed in this environment.
