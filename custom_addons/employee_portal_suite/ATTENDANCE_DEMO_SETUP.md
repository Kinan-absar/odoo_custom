# Attendance demo — version 18.0.1.20.135

## Install and create
1. Replace employee_portal_suite with this complete folder on your development/staging branch.
2. Upgrade Employee Portal Suite in Odoo.
3. Sign in as a Settings administrator. Open Employee Portal → Attendance Demo Setup (a top-level menu inside the app).
4. Set the site latitude/longitude to the location where you will record. Default coordinates are only an example. Keep the desired geofence radius (default 200 m).
5. Review timezone, company, employee name, login and generated password. Copy the login/password before closing the wizard. No invitation email is sent.
6. Click Create Demo Employee & History. Then use Open Demo Attendance to see all rows and offline columns.

Nothing is created automatically during install/upgrade. Reopening setup starts a new form with a new random login; click Create only when you want another demo employee. Existing users and attendance are never replaced. One wizard creates once even if the button is called again after completion.

## Included data
- Alex Morgan (Attendance Demo), linked to a portal user with attendance access.
- Demo — Riverside Project and Demo — Riverside Site, with the selected geofence.
- Employee assigned to the demo site using both the primary and multiple-location fields.
- Ten completed 08:00–16:00 sessions on the previous ten weekdays in the selected timezone.
- Five normal portal sessions.
- Three offline check-in/check-out pairs, with unique synthetic event IDs and synchronization timestamps.
- Two outside-site checkouts with GPS positions beyond the configured radius: one Pending Review and one Resolved.
- All rows clearly marked as demo examples in portal history; offline rows show Offline · Synced.
- No open attendance, payroll contract, live queued browser events, or pre-registered device.

## First phone visit / trusted device
Open the demo account on your phone FIRST using /web/login, then /my/employee/attendance. A previously unused browser token registers as trusted. If that browser token has registration history for another employee, it creates Pending Approval and notifies attendance managers instead. The backend Employee Portal → Attendance → Trusted Devices list will then contain the real phone. A fictitious Trusted record would block your phone, so none is seeded.

Use a different browser/device for the desktop restriction scene. Once your phone is trusted, that second browser is expected to show Device approval needed. Do not replace your trusted phone unless intentionally switching devices.

## Record these scenes
1. Backend Employees → demo employee → Work Information: assigned demo site.
2. Employees → Configuration → Work Locations → Demo — Riverside Site: project/geofence.
3. Setup result → Open Demo Attendance: list including offline columns; alternatively filter Attendances by the demo employee.
4. Employee Portal → Attendance → Outside Location Check-outs: pending outside-site example. Open it and use Mark as Resolved for the manager-review scene. After resolution it leaves that pending-only list but remains in the demo employee history.
5. Portal on your phone: populated recent history with Demo, Outside Location and Offline · Synced badges.
6. Backend Trusted Devices after the first phone visit: actual trusted phone.
7. Live check-in/out on the trusted phone at the configured location.
8. For actual offline recording: load Attendance online on the trusted phone first; disconnect; capture check-in/out and the pending queue; reconnect and show synchronization.

Offline samples are seeded historical examples, not proof that the phone has queued/synchronized events. Real offline queue data lives on the device and must be recorded there. This update does not bypass trusted-device or location checks.

## Validation
All Python and XML parsed; all manifest data files and new ACL references checked. Sample generator checked across 36 combinations of timezone/date/geofence, including DST transitions: ten closed sessions, no overlaps/future records, three offline pairs and two outside-site flags. The attendance controller is unchanged. Device registration now permits per-employee token records and requires manager approval when a token has history for another employee. Odoo is not installed in the build environment, so an actual Odoo installation/upgrade and UI run remains to be checked on staging.

Use a demo database: sample attendance is real stored demo data and is included in attendance reports. The generated password is shown in the admin-only setup form, which is transient; retain it securely or reset the demo user's password through Odoo if lost.

## Fix in 18.0.1.20.134
The demo site now uses the selected company partner as its required Work Address (address_id). This fixes the Work Location mandatory-field error during demo creation. Upgrade the module, reopen Attendance Demo Setup and create the demo again.

## Device registration fix in 18.0.1.20.135
A browser can carry its attendance token across account switches. Previously the database required token_hash to be globally unique while the lookup was per employee, so a new/demo employee could hit a duplicate-key error before Pending Approval was created.

- Unique registration is now (employee_id, token_hash).
- A token previously registered to another employee creates Pending Approval and calls the existing manager notification/activity flow.
- A different device for an employee who already has a trusted device also stays Pending Approval.
- Pending and revoked registrations keep their existing state on repeated visits.
- Concurrent registration of the same pair recovers the existing registration or asks Odoo to retry the transaction when a competing commit is outside its current snapshot.
- Upgrade migration identifies and removes the old global token unique constraint by its columns, including shortened/hashed Odoo constraint names. No device records are deleted.

Replace the module and upgrade Employee Portal Suite (not just restart). Refresh the existing demo account's Attendance page; there is no need to recreate the demo employee. In the backend open Employee Portal → Attendance → Trusted Devices to approve its pending device.

Regression checks exercised shared-browser pending approval and notification, repeated visits, manager-approved reuse, a second device for the same employee, revoked history, invalid tokens, concurrent same-token registration and transaction retry. Odoo/PostgreSQL are unavailable locally; installation and upgrade still require staging verification.
