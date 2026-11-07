# Native Employee Discuss architecture

Version 18.0.1.19.0 switches employee communication away from the custom portal chat/call frontend.

- Internal employees use standard Odoo Discuss.
- Employee portal users use Odoo's native public Discuss frontend for each authorized employee channel.
- Conversations are real `discuss.channel` records with native `discuss.channel.member` membership and `mail.message` messages.
- Native Discuss handles its own Store/bus unread state, attachments, replies/reactions and RTC UI.
- Employee-only channels involving at least one employee portal user are marked `is_employee_portal_channel` and exposed to the employee portal.
- Internal-only Discuss channels remain backend-only.
- Vendor/customer portal users are excluded because portal exposure/search requires an active `hr.employee` linked to the user.
- The Employee Portal keeps only a lightweight employee/channel chooser and unread badge; it does not implement the conversation or RTC engine.
- Telegram is an external alert only for messages; actual communication stays in Odoo Discuss.

## v18.0.1.20.0 — Native Discuss PWA

The standalone custom Chats frontend is no longer required. The employee communication surface is the existing native Odoo Discuss implementation at `/my/employee/discuss` and `/my/employee/discuss/channel/<id>`.

- Employee Portal Messages opens `/my/employee/discuss` in a new window, which immediately redirects to the most recent native Discuss channel. The old conversation hub is only kept at `/my/employee/discuss/manage` for starting conversations when needed.
- The native Discuss surface is installable as a PWA named **Chats**.
- The PWA uses the active company logo for install icons.
- No messages, attachments, calls, voice notes, reactions, presence, or RTC behavior are reimplemented by the PWA layer; all remain native Odoo Discuss features.
- Authenticated pages/messages are not cached by the service worker.
- When launched standalone, portal navigation chrome is hidden and the conversation hub becomes an app-like entry screen.
- The native channel page keeps the existing portal-safe Discuss patches, attachment uploader, mobile viewport handling, and native RTC bridge.

## Web Push notifications (20.34)

Chats now supports standards-based Web Push for installed PWAs and compatible desktop browsers. Employees enable notifications from the bell control on the Chats home page. The browser subscription is stored per Odoo user/device and native Discuss message/RTC events are sent through Web Push first. Telegram remains a fallback only when no active device accepts the push. iPhone/iPad users must add Chats to the Home Screen before enabling push notifications.
