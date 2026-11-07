# Portal Calling Feature — Setup & Notes

This adds 1:1 audio/video calling between Odoo users using the Employee Portal Suite.
It is a self-contained WebRTC feature and does not use Odoo Discuss/RTC.

## Calling directory

No manual Call Contact pairing is required anymore.

Every active Odoo user with either of these standard user types appears automatically in the call directory:
- Internal User (`base.group_user`)
- Portal User (`base.group_portal`)

Supported calling combinations:
- Portal → Internal
- Internal → Portal
- Portal → Portal
- Internal → Internal

The current user is excluded from their own directory. The call panel includes a search box and labels users as Portal or Internal.

## Backend

Employee Portal > Call History remains available to Employee Portal administrators.
The old Call Contacts model is retained only for database/backward compatibility and is no longer used to authorize or populate calls.

## Required setup after install/upgrade

1. Upgrade `employee_portal_suite`.
2. Deploy over HTTPS. WebRTC media APIs do not work over plain HTTP except localhost.
3. If users are behind restrictive NAT/firewalls, configure a TURN server using:
   - `employee_portal_suite.turn_url`
   - `employee_portal_suite.turn_username`
   - `employee_portal_suite.turn_credential`

## Security model

- Only authenticated active Portal/Internal users are returned by the call directory.
- A caller cannot call themselves.
- Call session access remains participant-scoped.
- Signalling rows remain recipient-scoped.
- Admins can read Call History.

## Known limitations

- Signalling is polled every 2 seconds rather than pushed through the Odoo mail bus.
- Calls are 1:1 only; no group calls.
- No call recording or busy-state handling yet.
- Frontend calling mounts on pages using the Employee Portal layout; backend calling mounts in the Odoo web client.
