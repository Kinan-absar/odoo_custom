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
        channel.sudo().write({
            'is_employee_portal_channel': True,
            'employee_portal_thread_id': self.id,
        })

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
        """Return/create the canonical native Discuss conversation.

        New conversations are created through native Discuss membership APIs.
        In particular, recipients are added with ``_add_members`` rather than by
        writing ``channel_member_ids`` directly. Odoo 18 uses that path to emit
        ``discuss.channel/joined`` on each new member's personal bus, which lets
        an already-open Discuss client subscribe to the new channel immediately.
        """
        self.ensure_one()
        if self.discuss_channel_id:
            channel = self.discuss_channel_id.sudo()
            vals = {}
            if not channel.is_employee_portal_channel:
                vals['is_employee_portal_channel'] = True
            if channel.employee_portal_thread_id != self:
                vals['employee_portal_thread_id'] = self.id
            if vals:
                channel.write(vals)
            return channel

        users = self.participant_ids.sudo().filtered(lambda user: user.active and user.partner_id)
        partner_ids = users.partner_id.ids
        if len(partner_ids) < 2:
            return self.env['discuss.channel']

        Channel = self.env['discuss.channel'].sudo()
        # Reuse an exact native DM when one already exists.
        channel = self.env['discuss.channel']
        if not self.is_group and len(partner_ids) == 2:
            self.env['discuss.channel'].flush_model()
            self.env['discuss.channel.member'].flush_model()
            self.env.cr.execute("""
                SELECT M.channel_id
                  FROM discuss_channel C
                  JOIN discuss_channel_member M ON M.channel_id = C.id
                 WHERE C.channel_type = 'chat'
                   AND M.partner_id IN %s
                   AND NOT EXISTS (
                       SELECT 1 FROM discuss_channel_member M2
                        WHERE M2.channel_id = C.id AND M2.partner_id NOT IN %s
                   )
              GROUP BY M.channel_id
                HAVING ARRAY_AGG(DISTINCT M.partner_id ORDER BY M.partner_id) = %s
                 LIMIT 1
            """, (tuple(partner_ids), tuple(partner_ids), sorted(partner_ids)))
            row = self.env.cr.fetchone()
            if row:
                channel = Channel.browse(row[0])

        if not channel:
            # Create with the request/current employee as the initial persona.
            # discuss.channel.create() natively adds env.user; then _add_members()
            # emits the joined event for every remaining recipient.
            current_partner = self.env.user.partner_id
            if current_partner.id not in partner_ids:
                current_partner = users[:1].partner_id
            create_env = Channel.with_user(current_partner.user_ids[:1] or self.env.user).sudo()
            channel = create_env.create({
                'channel_type': 'group' if self.is_group or len(partner_ids) > 2 else 'chat',
                'name': self.name or ', '.join(users.partner_id.mapped('name')),
                'is_employee_portal_channel': True,
            })
            existing = channel.channel_member_ids.partner_id
            missing = users.partner_id - existing
            if missing:
                channel.with_user(create_env.env.user).sudo()._add_members(
                    partners=missing,
                    post_joined_message=False,
                    open_chat_window=False,
                )
        else:
            channel.channel_member_ids.sudo().write({'unpin_dt': False})
            channel.sudo()._broadcast(partner_ids)

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
