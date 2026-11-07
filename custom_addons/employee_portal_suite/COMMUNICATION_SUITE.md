# Employee Communication Suite - 18.0.1.18.0

## Architecture

- Internal users use native Odoo Discuss for messaging.
- Employee portal users use the Employee Portal Messages interface.
- Portal-linked conversations share native `discuss.channel`, `discuss.channel.member`, and `mail.message` records with Discuss.
- Internal-only Discuss conversations are not exposed in the Employee Portal.
- Portal-linked channels are marked with `is_employee_portal_channel` and linked to `portal.chat.thread`.
- Calls continue to use the existing Employee Portal WebRTC call service to preserve the stable portal/mobile experience while exposing audio, video, group calling, screen sharing, participant management, presence, history, and reconnect behavior.

## Messaging features

- Direct and group chat
- Group names and participant list
- Native Discuss-backed messages
- Date separators and per-message time
- Sender grouping
- Attachments (10 MB per file)
- Replies
- Reactions
- Employee mentions / native partner notifications
- Typing indicator
- Native read marker synchronization and Seen by display
- Separate Messages icon and unread counter
- Internal Discuss recipient search includes employee portal users while excluding non-employee vendor portal users
- Backend bridge notification/live refresh fallback for portal-originated messages
- Telegram notifications for new portal-linked chat messages

## Calling features

- Separate Calls icon and missed-call counter
- Direct audio calls
- Direct video calls
- Group audio/video calls from group chat
- Add participants during an active call
- Screen sharing and fullscreen shared-screen view
- Participant roster
- Employee profile photos
- Portal/mobile speaker control where browser permits
- Ringing/in-page incoming-call notification
- Telegram incoming-call and missed-call alerts
- Presence: Online / Away / Offline / In Call
- Recent call history and missed calls
- Automatic reconnect / ICE recovery

## Notes

Native Odoo Discuss is the source of truth for portal-linked messaging. The portal call UI remains the proven custom WebRTC implementation rather than mounting Odoo's backend RTC frontend directly into the website portal. This avoids granting portal users backend Discuss access while retaining employee-only access controls.
