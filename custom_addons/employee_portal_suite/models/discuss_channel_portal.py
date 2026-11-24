from odoo import _, api, fields, models, tools


from odoo.exceptions import AccessError


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    is_employee_portal_channel = fields.Boolean(
        string='Employee Portal Conversation', default=False, copy=False, index=True,
        help='Technical marker: this Discuss conversation is exposed in the Employee Portal.',
    )
    employee_portal_thread_id = fields.Many2one(
        'portal.chat.thread', string='Employee Portal Conversation', copy=False,
        ondelete='set null', index=True,
    )



    employee_portal_access = fields.Selection(
        selection=[
            ('disabled', 'Not Available'),
            ('read_only', 'Read Only'),
            ('read_write', 'Read & Write'),
        ],
        string='Employee Portal Access',
        default='disabled',
        copy=False,
        help='Controls whether employee portal users can see this Channel and whether they may interact with it.',
    )
    employee_portal_all_employees = fields.Boolean(
        string='All Portal Employees',
        default=False,
        copy=False,
        help='Automatically include all active employee portal users in this Channel.',
    )
    employee_portal_employee_ids = fields.Many2many(
        'hr.employee',
        'discuss_channel_portal_employee_rel',
        'channel_id',
        'employee_id',
        string='Portal Employees',
        copy=False,
        domain="[('active', '=', True), ('user_id', '!=', False), ('user_id.share', '=', True)]",
        help='Specific employee portal users who should be members of this Channel.',
    )
    employee_portal_department_ids = fields.Many2many(
        'hr.department',
        'discuss_channel_portal_department_rel',
        'channel_id',
        'department_id',
        string='Portal Departments',
        copy=False,
        help='Active employee portal users in these departments are automatically included in this Channel.',
    )

    def _is_employee_portal_user(self, user=None):
        user = user or self.env.user
        return bool(
            user
            and user.active
            and user.share
            and self.env['hr.employee'].sudo().search_count([
                ('active', '=', True), ('user_id', '=', user.id),
            ])
            and not user.has_group('employee_portal_suite.group_attendance_only')
        )

    def _portal_channel_is_read_only_for(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return bool(
            self.channel_type == 'channel'
            and self.employee_portal_access == 'read_only'
            and self._is_employee_portal_user(user)
            and user.partner_id in self.channel_member_ids.partner_id
        )



    def _employee_portal_candidate_users(self):
        return self.env['res.users']

    def _sync_employee_portal_members(self):
        if not self.env.context.get('skip_employee_portal_channel_sync'):
            self.sudo().filtered('is_employee_portal_channel').with_context(
                skip_employee_portal_channel_sync=True,
            ).write({
                'employee_portal_access': 'disabled',
                'allow_public_upload': False,
            })

    @api.model_create_multi
    def create(self, vals_list):
        channels = super().create(vals_list)
        channels._sync_employee_portal_members()
        return channels

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('skip_employee_portal_channel_sync') and any(
            key in vals
            for key in (
                'employee_portal_access',
                'employee_portal_all_employees',
                'employee_portal_employee_ids',
                'employee_portal_department_ids',
                'channel_type',
            )
        ):
            self._sync_employee_portal_members()
        return result






    def message_post(self, **kwargs):
        for channel in self:
            if channel._portal_channel_is_read_only_for(self.env.user):
                raise AccessError(_('This Channel is read-only in the Employee Portal.'))
        message = super().message_post(**kwargs)
        # Native Discuss remains the source of truth. Telegram is only an external alert.
        for channel in self.sudo().filtered('is_employee_portal_channel'):
            if not message or message.model != 'discuss.channel' or message.res_id != channel.id:
                continue
            if message.message_type not in ('comment', 'email'):
                continue
            # Native Discuss allows attachment-only messages. Those must trigger
            # the same Telegram alert as text messages.
            if not message.body and not message.attachment_ids:
                continue
            author_partner = message.author_id
            recipients = channel.channel_member_ids.partner_id - author_partner
            users = self.env['res.users'].sudo().search([
                ('active', '=', True), ('partner_id', 'in', recipients.ids),
            ])
            emp_user_ids = set(self.env['hr.employee'].sudo().search([
                ('active', '=', True), ('user_id', 'in', users.ids),
            ]).mapped('user_id').ids)
            users = users.filtered(lambda u: u.id in emp_user_ids)
            preview = tools.html2plaintext(message.body or '').strip().replace('\n', ' ')[:160]
            if message.attachment_ids:
                names = ', '.join(message.attachment_ids.mapped('name')[:3])
                attachment_note = ('Attachment: ' if len(message.attachment_ids) == 1 else 'Attachments: ') + names
                preview = (preview + (' - ' if preview else '') + attachment_note)[:220]
            sender = author_partner.name or 'Employee'
            push_service = self.env['employee.portal.webpush.service'].sudo()
            telegram_service = self.env['employee.portal.telegram.service'].sudo()
            for user in users:
                path = f'/my/employee/discuss?open_channel={channel.id}'
                pushed = False
                try:
                    pushed = push_service.send_to_user(
                        user,
                        sender,
                        preview or 'New message',
                        path=path,
                        kind='message',
                        tag=f'employee-chats-channel-{channel.id}',
                    )
                except Exception:
                    pushed = False
                # Telegram is retained as a fallback only when no device accepted
                # the native Web Push notification.
                if not pushed:
                    try:
                        telegram_service.with_context(skip_webpush=True).send_to_user(
                            user, sender, preview or 'New message', path=path
                        )
                    except Exception:
                        continue
        return message


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    portal_is_typing = fields.Boolean(default=False, copy=False)
    portal_typing_dt = fields.Datetime(copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        members = super().create(vals_list)
        if not self.env.context.get('skip_ep_channel_refresh'):
            members.channel_id._sync_employee_portal_members()
        return members

    def unlink(self):
        channels = self.channel_id
        res = super().unlink()
        if not self.env.context.get('skip_ep_channel_refresh'):
            channels.exists()._sync_employee_portal_members()
        return res
