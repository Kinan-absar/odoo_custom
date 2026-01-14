from odoo import models, fields


class ResPartner(models.Model):
    _inherit = "res.partner"

    statement_balance = fields.Monetary(
        string="Statement Balance",
        compute="_compute_statement_balance",
        currency_field="currency_id",
    )

    def _compute_statement_balance(self):
        for partner in self:
            balance = 0.0

            aml = self.env["account.move.line"].search([
                ("partner_id", "=", partner.id),
                ("parent_state", "=", "posted"),
                ("account_id.account_type", "in", (
                    "asset_receivable",
                    "liability_payable",
                )),
            ])

            for line in aml:
                if line.account_id.account_type == "asset_receivable":
                    balance += line.debit - line.credit
                else:
                    balance += line.credit - line.debit

            partner.statement_balance = balance

    def action_open_customer_statement_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Customer Statement",
            "res_model": "customer.statement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }

    def action_open_vendor_statement_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Vendor Statement",
            "res_model": "vendor.statement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }
