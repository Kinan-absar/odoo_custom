from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    absar_is_sales_customer = fields.Boolean(
        string='Customer / Client',
        help='Include this contact in the customer selector for Sales Quotations and the Employee Portal.',
        index=True,
    )
