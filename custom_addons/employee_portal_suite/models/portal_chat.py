from odoo import Command, fields, models


class PortalChatThread(models.Model):
    _name = 'portal.chat.thread'
    _description = 'Employee Portal Chat'
    _inherit = ['mail.thread']
    _order = 'discuss_last_interest_dt desc, last_message_date desc, id desc'

    name = fields.Char(required=True, default='Conversation')
    participant_ids = fields.Many2many(
        'res.users', 'portal_chat_thread_user_rel', 'thread_id', 'user_id',
        string='Participants', required=True,
    )
    is_group = fields.Boolean(default=False)
    direct_key = fields.Char(index=True, copy=False)
    last_message_date = fields.Datetime(default=fields.Datetime.now, index=True)
    discuss_channel_id = fields.Many2one(
        'discuss.channel', string='Discuss Conversation', copy=False,
        ondelete='set null', index=True,
    )
    discuss_last_interest_dt = fields.Datetime(
        related='discuss_channel_id.last_interest_dt', store=True, index=True,
    )

    def _migrate_legacy_messages_to_discuss(self, channel):
        """Copy the old portal.chat.thread history once into its Discuss channel.

        Direct mail.message creation is intentional here: migration must preserve
        historical authors/dates without notifying everyone about old messages.
        New messages are posted through discuss.channel.message_post afterwards.
        """
        self.ensure_one()
        legacy_messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'portal.chat.thread'),
            ('res_id', '=', self.id),
            ('message_type', '=', 'comment'),
        ], order='id asc')
        if not legacy_messages:
            return

        Message = self.env['mail.message'].sudo()
        vals_list = []
        for message in legacy_messages:
            vals_list.append({
                'model': 'discuss.channel',
                'res_id': channel.id,
                'body': message.body,
                'author_id': message.author_id.id or False,
                'email_from': message.email_from,
                'message_type': 'comment',
                'subtype_id': message.subtype_id.id or self.env.ref('mail.mt_comment').id,
                'date': message.date,
                'subject': message.subject,
            })
        if vals_list:
            Message.create(vals_list)

    def _bind_discuss_channel(self, channel):
        """Bind this wrapper to an existing Discuss channel and migrate history."""
        self.ensure_one()
        channel = channel.sudo().exists()
        if not channel:
            return self.env['discuss.channel']
        if self.discuss_channel_id:
            return self.discuss_channel_id

        self._migrate_legacy_messages_to_discuss(channel)
        self.sudo().write({'discuss_channel_id': channel.id})

        # Make the migrated conversation visible in native Discuss immediately.
        channel.channel_member_ids.sudo().write({'unpin_dt': False})
        channel.sudo().write({'last_interest_dt': fields.Datetime.now()})
        try:
            channel.sudo()._broadcast(channel.channel_member_ids.partner_id.ids)
        except Exception:
            # The channel itself is already valid; broadcast is UI convenience only.
            pass
        return channel

    def _ensure_discuss_channel(self):
        """Return/create the canonical native Discuss conversation for this thread."""
        self.ensure_one()
        if self.discuss_channel_id:
            return self.discuss_channel_id.sudo()

        users = self.participant_ids.sudo().filtered(lambda user: user.active and user.partner_id)
        partner_ids = users.partner_id.ids
        if len(partner_ids) < 2:
            return self.env['discuss.channel']

        Channel = self.env['discuss.channel'].sudo()
        if self.is_group or len(partner_ids) > 2:
            channel = Channel.create_group(partner_ids, name=self.name or '')
        else:
            # channel_get reuses Odoo's canonical 1-to-1 Discuss conversation when
            # these two employees already spoke in native Discuss.
            channel = Channel.channel_get(list(partner_ids), pin=True, force_open=False)

        return self._bind_discuss_channel(channel)


class PortalChatRead(models.Model):
    _name = 'portal.chat.read'
    _description = 'Employee Portal Chat Read State'
    _rec_name = 'thread_id'

    thread_id = fields.Many2one('portal.chat.thread', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    last_read_at = fields.Datetime(default=fields.Datetime.now, index=True)

    _sql_constraints = [
        ('portal_chat_read_unique', 'unique(thread_id, user_id)', 'Only one read state is allowed per user and conversation.'),
    ]
