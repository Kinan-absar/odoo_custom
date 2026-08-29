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
