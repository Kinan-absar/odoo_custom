from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    material_request_id = fields.Many2one(
        "material.request",
        string="Material Request",
        index=True,
        ondelete="set null",
        copy=False,
    )
