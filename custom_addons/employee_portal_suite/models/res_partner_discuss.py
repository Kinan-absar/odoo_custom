from odoo import api, models
from odoo.fields import Domain


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.readonly
    @api.model
    def _search_for_channel_invite(self, store, search_term, channel_id=None, limit=30):
        """Use the employee directory for native Discuss "new chat" / invite search.

        Odoo 19 routes both the Discuss search (``/discuss/search``, used by the
        new-chat dialog) and the channel-invite search through this method, and it
        intentionally limits results to non-share users. Our employee portal users
        are ``share=True``, so native Discuss cannot find them.

        For internal users and for employee portal users, expose active users linked
        to an active ``hr.employee``. Vendor/customer portal accounts keep Odoo's
        standard behaviour and are never included in this directory because they
        are not linked to an active employee.
        """
        is_employee_portal = bool(
            self.env.user.share
            and self.env['hr.employee'].sudo().search_count([
                ('active', '=', True), ('user_id', '=', self.env.user.id),
            ])
            and not self.env.user.has_group('employee_portal_suite.group_attendance_only')
        )
        if not self.env.user._is_internal() and not is_employee_portal:
            return super()._search_for_channel_invite(
                store, search_term, channel_id=channel_id, limit=limit
            )

        channel = self.env['discuss.channel'].sudo()
        if channel_id:
            try:
                channel = channel.browse(int(channel_id)).exists()
            except (TypeError, ValueError):
                channel = self.env['discuss.channel'].sudo()
            if channel and self.env.user.partner_id not in channel.channel_member_ids.partner_id:
                return {'count': 0, 'partner_ids': []}

        employee_users = self.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('user_id', '!=', False),
        ]).mapped('user_id').filtered(lambda u: u.active and u.partner_id)
        employee_partner_ids = employee_users.partner_id.ids
        excluded_partner_ids = [self.env.user.partner_id.id]
        if channel:
            excluded_partner_ids += channel.channel_member_ids.partner_id.ids

        domain = Domain.AND([
            [('active', '=', True)],
            [('id', 'in', employee_partner_ids)],
            [('id', 'not in', excluded_partner_ids)],
        ])
        term = (search_term or '').strip()
        if term:
            domain = Domain.AND([
                domain,
                Domain.OR([
                    [('name', 'ilike', term)],
                    [('email', 'ilike', term)],
                ]),
            ])

        Partner = self.sudo()
        partners = Partner.search(domain, order='name, id', limit=limit)
        partners._search_for_channel_invite_to_store(store, channel)
        return {
            'count': Partner.search_count(domain),
            'partner_ids': partners.ids,
        }
