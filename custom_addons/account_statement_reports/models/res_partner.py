from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    statement_balance = fields.Monetary(string="Statement Balance", compute="_compute_statement_balances", currency_field="currency_id")
    customer_statement_balance = fields.Monetary(string="Customer Statement Balance", compute="_compute_statement_balances", currency_field="currency_id")
    vendor_statement_balance = fields.Monetary(string="Vendor Statement Balance", compute="_compute_statement_balances", currency_field="currency_id")

    @api.depends_context("company")
    def _compute_statement_balances(self):
        for partner in self:
            lines = self.env["account.move.line"].search([
                ("partner_id", "=", partner.id),
                ("parent_state", "=", "posted"),
                ("company_id", "=", self.env.company.id),
                ("account_id.account_type", "in", ("asset_receivable", "liability_payable")),
            ])
            receivable = sum((l.debit or 0.0) - (l.credit or 0.0) for l in lines if l.account_id.account_type == "asset_receivable")
            payable = sum((l.credit or 0.0) - (l.debit or 0.0) for l in lines if l.account_id.account_type == "liability_payable")
            partner.customer_statement_balance = receivable
            partner.vendor_statement_balance = payable
            partner.statement_balance = receivable - payable

    def action_open_account_statement(self):
        self.ensure_one()
        statement_type = "payable" if self.supplier_rank and not self.customer_rank else "receivable"
        return self.env["account.statement"].with_context(
            default_statement_type=statement_type,
            default_partner_id=self.id,
            default_company_id=self.env.company.id,
        ).action_open_new_workspace()

    # Backward-compatible methods for existing buttons/bookmarks.
    def action_open_customer_statement_wizard(self):
        self.ensure_one()
        return self.env["account.statement"].with_context(
            default_statement_type="receivable",
            default_partner_id=self.id,
            default_company_id=self.env.company.id,
        ).action_open_new_workspace()

    def action_open_vendor_statement_wizard(self):
        self.ensure_one()
        return self.env["account.statement"].with_context(
            default_statement_type="payable",
            default_partner_id=self.id,
            default_company_id=self.env.company.id,
        ).action_open_new_workspace()
