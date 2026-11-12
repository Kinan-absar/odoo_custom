from copy import deepcopy
from odoo import api, fields, models, _
from odoo.osv import expression


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Original Sales field name deliberately retained: existing contact values
    # must not be replaced by a second, initially empty customer classification.
    absar_is_sales_customer = fields.Boolean(
        string='Customer / Client',
        help='Include this contact in the customer selector for Sales Quotations and the portal.',
        index=True,
    )
    # Obsolete v0.9.x column: retain data but never use it to override the original
    # checkbox. Upgrade migration restores PBW-only databases, not original flags.
    pbw_is_sales_customer = fields.Boolean(
        string='Legacy Workspace Customer Flag', readonly=True, copy=False,
        help='Historical workspace value. Use Customer / Client instead.', index=True,
    )

    @api.model
    def _pbw_sales_customer_eligibility_domain(self):
        return [('absar_is_sales_customer', '=', True)]

    @api.model
    def _pbw_sales_customer_domain(self, company):
        return expression.AND([
            [('active', '=', True), '|', ('company_id', '=', False),
             ('company_id', 'in', company.ids)],
            self._pbw_sales_customer_eligibility_domain(),
        ])

    @api.model
    def _pbw_sales_customer_source_labels(self):
        return [_('Customer / Client')]

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form':
            # If original Sales also adds its own widget, keep that widget, not
            # a second copy from PBW. Do not modify cached or other addons' XML.
            ours = arch.xpath(".//field[@id='pbw_sales_customer_flag']")
            native = arch.xpath(".//field[@name='absar_is_sales_customer' and not(@id='pbw_sales_customer_flag')]")
            visible_native = [node for node in native if node.get('invisible') not in ('1', 'True', 'true')]
            if ours and visible_native:
                arch = deepcopy(arch)
                for node in arch.xpath(".//field[@id='pbw_sales_customer_flag']"):
                    node.getparent().remove(node)
        return arch, view
