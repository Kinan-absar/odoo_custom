from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Odoo 18 already provides the report font picker on res.company.  We only
    # add Noto Sans Arabic because it rendered well in the customer's Odoo.sh
    # environment.  All of Odoo's native choices (including Tajawal) remain.
    font = fields.Selection(
        selection_add=[("Noto Sans Arabic", "Noto Sans Arabic")],
        ondelete={"Noto Sans Arabic": "set default"},
    )
