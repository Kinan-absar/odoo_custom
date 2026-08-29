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
