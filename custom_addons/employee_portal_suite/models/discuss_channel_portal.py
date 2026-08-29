from odoo import api, fields, models, tools


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



    def add_members(self, partner_ids=None, guest_ids=None, invite_to_rtc_call=False,
                    open_chat_window=False, post_joined_message=True):
        """Allow the native Discuss invite action for Employee Portal members.

        The normal native method is kept for internal users. Portal employees may
        only add partners that belong to active employees, and only to a portal
        employee conversation in which they are already a member.
        """
        is_employee_portal = bool(
            self.env.user.share
            and self.env['hr.employee'].sudo().search_count([
                ('active', '=', True), ('user_id', '=', self.env.user.id),
            ])
            and not self.env.user.has_group('employee_portal_suite.group_attendance_only')
        )
        if not is_employee_portal:
            return super().add_members(
                partner_ids=partner_ids,
                guest_ids=guest_ids,
                invite_to_rtc_call=invite_to_rtc_call,
                open_chat_window=open_chat_window,
                post_joined_message=post_joined_message,
            )

        if guest_ids:
            return self.env['discuss.channel.member']

        channels = self.sudo().exists()
        current_partner = self.env.user.partner_id
        if not channels or any(
            current_partner not in ch.channel_member_ids.partner_id
            or ch.channel_type not in ('chat', 'group')
            for ch in channels
        ):
            return self.env['discuss.channel.member']

        requested = self.env['res.partner'].sudo().browse(partner_ids or []).exists()
        employee_partner_ids = set(self.env['hr.employee'].sudo().search([
            ('active', '=', True), ('user_id', '!=', False), ('user_id.active', '=', True),
        ]).mapped('user_id.partner_id').ids)
        partners = requested.filtered(lambda p: p.id in employee_partner_ids)
        if partners != requested:
            return self.env['discuss.channel.member']

        return channels._add_members(
            partners=partners,
            invite_to_rtc_call=invite_to_rtc_call,
            open_chat_window=open_chat_window,
            post_joined_message=post_joined_message,
            inviting_partner=current_partner,
        )

    def _refresh_employee_portal_channel_flag(self):
        Employee = self.env['hr.employee'].sudo()
        for channel in self.sudo():
            if channel.channel_type not in ('chat', 'group'):
                continue
            partners = channel.channel_member_ids.partner_id.filtered(lambda p: p.active)
            if len(partners) < 2:
                continue
            users = self.env['res.users'].sudo().search([
                ('active', '=', True), ('partner_id', 'in', partners.ids),
            ])
            employee_user_ids = set(Employee.search([
                ('active', '=', True), ('user_id', 'in', users.ids),
            ]).mapped('user_id').ids)
            employee_users = users.filtered(lambda u: u.id in employee_user_ids)
            # Expose only employee-only chats with at least one portal employee.
            all_partners_are_employees = set(partners.ids).issubset(set(employee_users.partner_id.ids))
            should_expose = all_partners_are_employees and len(employee_users) >= 2 and any(u.share for u in employee_users)
            if channel.is_employee_portal_channel != should_expose:
                channel.with_context(skip_ep_channel_refresh=True).write({
                    'is_employee_portal_channel': should_expose,
                })
        return True

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        # Native Discuss remains the source of truth. Telegram is only an external alert.
        for channel in self.sudo().filtered('is_employee_portal_channel'):
            if not message or message.model != 'discuss.channel' or message.res_id != channel.id:
                continue
            if message.message_type not in ('comment', 'email') or not message.body:
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
            sender = author_partner.name or 'Employee'
            service = self.env['employee.portal.telegram.service'].sudo()
            for user in users:
                try:
                    path = f'/my/employee/discuss/channel/{channel.id}' if user.share else '/odoo/discuss'
                    service.send_to_user(user, f'New message from {sender}', preview or 'New message', path=path)
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
            members.channel_id._refresh_employee_portal_channel_flag()
        return members

    def unlink(self):
        channels = self.channel_id
        res = super().unlink()
        if not self.env.context.get('skip_ep_channel_refresh'):
            channels.exists()._refresh_employee_portal_channel_flag()
        return res
