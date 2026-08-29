from odoo import api, models
from odoo.osv import expression
from odoo.addons.mail.tools.discuss import Store


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.readonly
    @api.model
    def im_search(self, name, limit=20, excluded_ids=None):
        """Include employee portal users in Discuss new-chat suggestions.

        Standard Odoo intentionally limits Discuss IM search to non-share users.
        Our employee portal users are share=True, so native Discuss cannot find
        them. Extend only this IM search, and only with active users linked to an
        active hr.employee. Vendor/customer portal accounts remain excluded.
        """
        if excluded_ids is None:
            excluded_ids = []

        # Internal users use backend Discuss. Employee portal users now use the
        # native public Discuss frontend as well, so both need the same employee
        # directory. Non-employee customer/vendor portal accounts keep Odoo's
        # standard behavior and are never included in this directory.
        is_employee_portal = bool(
            self.env.user.share
            and self.env['hr.employee'].sudo().search_count([
                ('active', '=', True), ('user_id', '=', self.env.user.id),
            ])
            and not self.env.user.has_group('employee_portal_suite.group_attendance_only')
        )
        if not self.env.user._is_internal() and not is_employee_portal:
            return super().im_search(name, limit=limit, excluded_ids=excluded_ids)

        employee_user_ids = self.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('user_id', '!=', False),
        ]).mapped('user_id').filtered(lambda user: user.active).ids

        domain = [
            ('id', '!=', self.env.user.id),
            ('name', 'ilike', name),
            ('active', '=', True),
            ('partner_id', 'not in', excluded_ids),
        ]
        if self.env.user._is_internal():
            # Preserve the normal internal-user directory and additionally expose
            # employee portal users that Odoo normally filters out via share=True.
            domain += ['|', ('share', '=', False), ('id', 'in', employee_user_ids)]
        else:
            # Employee portal users only see actual active employees.
            domain += [('id', 'in', employee_user_ids)]

        users = self.env['res.users'].sudo().search(
            domain, order='share, name, id', limit=limit
        )
        return Store(users.partner_id).get_result()

    @api.readonly
    @api.model
    def search_for_channel_invite(self, search_term, channel_id=None, limit=30):
        """Let Employee Portal users use Odoo's *native* Invite People panel.

        Odoo's standard implementation intentionally filters on
        ``user_ids.share = False``. Employee portal accounts are ``share=True``,
        therefore the native ChannelInvitation panel otherwise finds nobody.
        For authenticated employee portal users, expose only active employees
        (internal + employee portal) and never vendor/customer portal accounts.
        """
        is_employee_portal = bool(
            self.env.user.share
            and self.env['hr.employee'].sudo().search_count([
                ('active', '=', True), ('user_id', '=', self.env.user.id),
            ])
            and not self.env.user.has_group('employee_portal_suite.group_attendance_only')
        )
        if not is_employee_portal:
            return super().search_for_channel_invite(
                search_term, channel_id=channel_id, limit=limit
            )

        channel = self.env['discuss.channel'].sudo()
        if channel_id:
            try:
                channel = channel.browse(int(channel_id)).exists()
            except (TypeError, ValueError):
                channel = self.env['discuss.channel'].sudo()
            if channel:
                current_partner = self.env.user.partner_id
                if current_partner not in channel.channel_member_ids.partner_id:
                    return {'count': 0, 'data': {}}

        employee_users = self.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('user_id', '!=', False),
        ]).mapped('user_id').filtered(lambda u: u.active)
        employee_partner_ids = employee_users.partner_id.ids
        excluded_partner_ids = [self.env.user.partner_id.id]
        if channel:
            excluded_partner_ids += channel.channel_member_ids.partner_id.ids

        domain = [
            ('active', '=', True),
            ('id', 'in', employee_partner_ids),
            ('id', 'not in', excluded_partner_ids),
        ]
        term = (search_term or '').strip()
        if term:
            domain = expression.AND([
                domain,
                expression.OR([
                    [('name', 'ilike', term)],
                    [('email', 'ilike', term)],
                ]),
            ])

        Partner = self.sudo()
        partners = Partner.search(domain, order='name, id', limit=limit)
        store = Store()
        partners._search_for_channel_invite_to_store(store, channel)
        return {
            'count': Partner.search_count(domain),
            'data': store.get_result(),
        }

