# Telegram approval notifications

1. In Telegram, open @BotFather and run `/newbot`.
2. Create a bot and copy the Bot Token. Keep it private.
3. In Odoo, open **Employee Portal > Telegram Notifications** and create one configuration record.
4. Paste the Bot Token and save.
5. Click **Test Bot**. Odoo resolves and stores the bot username.
6. Confirm Odoo's System Parameter `web.base.url` is the public HTTPS URL users use to access Odoo.
7. Click **Configure Webhook & Enable**. Odoo registers its webhook with Telegram.
8. Each employee/approver opens the Employee Portal dashboard and clicks **Telegram Notifications > Connect**.
9. Telegram opens the bot. Press **START**. The bot replies that it is connected to the Odoo account.
10. Approval-stage notifications are now sent automatically with an **Open in Odoo** button.

Telegram is notification-only. Approval and rejection remain in Odoo.
