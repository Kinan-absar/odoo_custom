from odoo import api, models
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

        # Keep this extension for internal Discuss users only. Portal employees
        # use the dedicated portal messaging UI and do not need native IM search.
        if not self.env.user._is_internal():
            return super().im_search(name, limit=limit, excluded_ids=excluded_ids)

        employee_user_ids = self.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('user_id', '!=', False),
        ]).mapped('user_id').filtered(lambda user: user.active).ids

        users = self.env['res.users'].sudo().search([
            ('id', '!=', self.env.user.id),
            ('name', 'ilike', name),
            ('active', '=', True),
            ('partner_id', 'not in', excluded_ids),
            '|',
            ('share', '=', False),
            ('id', 'in', employee_user_ids),
        ], order='share, name, id', limit=limit)

        return Store(users.partner_id).get_result()
