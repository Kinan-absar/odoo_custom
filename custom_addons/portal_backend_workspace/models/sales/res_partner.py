from odoo import api, fields, models, _
from odoo.osv import expression


class ResPartner(models.Model):
    _inherit = 'res.partner'

    pbw_is_sales_customer = fields.Boolean(
        string='Workspace Customer / Client',
        help='Include this contact in the standalone Sales workspace. The optional Employee Portal bridge connects the original Sales customer checkbox.',
        index=True,
    )

    @api.model
    def _pbw_sales_customer_eligibility_domain(self):
        """Fixed provider hook; a bridge can add an existing customer flag."""
        return [('pbw_is_sales_customer', '=', True)]

    @api.model
    def _pbw_sales_customer_domain(self, company):
        return expression.AND([
            [('active', '=', True), '|', ('company_id', '=', False),
             ('company_id', 'in', company.ids)],
            self._pbw_sales_customer_eligibility_domain(),
        ])

    @api.model
    def _pbw_sales_customer_source_labels(self):
        """Readable provider status for the empty-selector message; no contact data."""
        return [_('Workspace Customer / Client')]
