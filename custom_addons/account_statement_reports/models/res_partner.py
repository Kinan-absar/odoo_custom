from odoo import models, fields, api, _


class ResPartner(models.Model):
    _inherit = "res.partner"

    statement_balance = fields.Monetary(
        string="Statement Balance",
        compute="_compute_statement_balances",
        currency_field="currency_id",
    )
    customer_statement_balance = fields.Monetary(
        string="Customer Statement Balance",
        compute="_compute_statement_balances",
        currency_field="currency_id",
    )
    vendor_statement_balance = fields.Monetary(
        string="Vendor Statement Balance",
        compute="_compute_statement_balances",
        currency_field="currency_id",
    )

    @api.depends_context("company")
    def _compute_statement_balances(self):
        """Keep the useful smart-button balances from the previous build.

        The actual statement display uses Odoo's native accounting-report engine,
        but these values still give an immediate receivable/payable snapshot
        on the partner form.
        """
        for partner in self:
            lines = self.env["account.move.line"].search([
                ("partner_id", "=", partner.id),
                ("parent_state", "=", "posted"),
                ("company_id", "=", self.env.company.id),
                ("account_id.account_type", "in", ("asset_receivable", "liability_payable")),
            ])
            receivable = sum(
                (line.debit or 0.0) - (line.credit or 0.0)
                for line in lines
                if line.account_id.account_type == "asset_receivable"
            )
            payable = sum(
                (line.credit or 0.0) - (line.debit or 0.0)
                for line in lines
                if line.account_id.account_type == "liability_payable"
            )
            partner.customer_statement_balance = receivable
            partner.vendor_statement_balance = payable
            partner.statement_balance = receivable - payable

    def _action_open_native_account_statement(self):
        """Open the dedicated native Account Statement report.

        The partner can then be selected/changed directly in the report's
        editable Partner filter. We deliberately avoid fragile JS-specific
        option injection so this remains upgrade-safe on Odoo 18.
        """
        self.ensure_one()
        report = self.env.ref("account_statement_reports.account_statement_native_report")
        return {
            "type": "ir.actions.client",
            "name": _("Account Statement Reports"),
            "tag": "account_report",
            "context": {"report_id": report.id},
        }

    def action_open_customer_statement_wizard(self):
        return self._action_open_native_account_statement()

    def action_open_vendor_statement_wizard(self):
        return self._action_open_native_account_statement()
