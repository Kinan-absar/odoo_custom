from odoo import models, fields

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    material_request_id = fields.Many2one(
        "material.request",
        string="Material Request",
        index=True,
        ondelete="set null",
    )
