from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_open_customer_statement_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Customer Statement",
            "res_model": "customer.statement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": self.id,
            },
        }

    def action_open_vendor_statement_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Vendor Statement",
            "res_model": "vendor.statement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": self.id,
            },
        }
