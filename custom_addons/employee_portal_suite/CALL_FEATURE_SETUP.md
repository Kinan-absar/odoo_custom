# Portal Calling Feature — Setup & Notes

This adds 1:1 audio/video calling between portal users and internal users.
It is **not** Odoo's Discuss/RTC system — it's a small, self-contained
WebRTC feature built specifically so it works on both the portal frontend
and the backend.

## What was added
- Models: `portal.call.session`, `portal.call.signal`, `portal.call.contact`
- Controller: `controllers/portal_call.py` (JSON-RPC endpoints under `/employee_portal/call/*`)
- Widget: `static/src/js/portal_call_widget.js` + matching SCSS, loaded in
  both `web.assets_frontend` and `web.assets_backend`
- Backend menu (**Employee Portal > Call Contacts**, **Call History**) —
  visible only to `group_employee_portal_admin`

## Required setup after install/upgrade
1. Upgrade the module (`-u employee_portal_suite`).
2. As an admin, go to **Employee Portal > Call Contacts** and create an
   allow-list entry for each portal user ↔ internal user pair that should
   be able to call each other. **Nobody can call anybody until this entry
   exists** — this is intentional (see "Security model" below).
3. Deploy over **HTTPS**. `getUserMedia`/WebRTC will not work over plain
   HTTP except on `localhost`.
4. If your users are behind restrictive corporate NAT/firewalls, a public
   STUN server alone (the default, Google's) may not be enough to connect.
   Add a TURN server via these `ir.config_parameter` keys:
   - `employee_portal_suite.turn_url` (e.g. `turn:turn.example.com:3478`)
   - `employee_portal_suite.turn_username`
   - `employee_portal_suite.turn_credential`

## Security model
- Calling is opt-in via an explicit allow-list (`portal.call.contact`),
  not a free-for-all directory — a portal user can never discover or ring
  an internal user unless an admin has paired them.
- Every session/signal row is scoped by `ir.rule` so a user (portal or
  internal) can only ever see call sessions/signals where they are a
  participant. Admins get a bypass rule for the Call History menu only.
- The JSON controllers use `csrf=False` (a deliberate choice, not an
  oversight) because every mutating action is independently re-validated
  against session participancy / the allow-list — CSRF protection would be
  redundant defense-in-depth here, not the primary guard.

## Known limitations / what to test before relying on this in production
- **Signalling is polled** (every 2s) rather than pushed via the mail bus,
  by design, to avoid any dependency on Discuss/RTC internals. This adds
  ~1-2s of latency to ringing and call setup — the audio/video itself is
  peer-to-peer WebRTC once connected and unaffected by this.
- Only 1:1 calls are supported (no group calls).
- No call recording, no ringtone/sound cues, no "busy" state if a user is
  already on another call — first call wins, a second incoming call while
  on a call will currently just overwrite the incoming-call UI. Fine for
  an MVP; worth hardening if this becomes a heavily used feature.
- The frontend widget mounts only on portal pages that use
  `employee_portal_layout` (via the `#epc-mount-marker` element it looks
  for) — if you have other portal templates that don't extend that layout,
  the call button won't appear there.
- Not yet tested against a live Odoo 18 instance — the models/controllers/
  security follow Odoo's standard patterns and the JS has been syntax-
  checked, but please test the full ring → accept → connect → hang-up flow
  end-to-end (ideally two different browsers/devices) before rolling out.
