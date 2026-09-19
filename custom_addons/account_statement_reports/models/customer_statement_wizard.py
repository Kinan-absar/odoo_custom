from odoo import models, fields


class CustomerStatementWizard(models.TransientModel):
    _name = "customer.statement.wizard"
    _description = "Customer Statement Wizard"

    partner_id = fields.Many2one(
        "res.partner", required=True,
        domain="['|', ('customer_rank', '>', 0), ('parent_id.customer_rank', '>', 0)]",
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
    )
    date_from = fields.Date()
    date_to = fields.Date()
    journal_ids = fields.Many2many(
        "account.journal",
        "customer_statement_wizard_journal_rel",
        "wizard_id", "journal_id",
        string="Journals",
        domain="[('company_id', '=', company_id)]",
    )
    account_ids = fields.Many2many(
        "account.account",
        "customer_statement_wizard_account_rel",
        "wizard_id", "account_id",
        string="Receivable Accounts",
        domain="[('account_type', '=', 'asset_receivable')]",
    )
    move_state = fields.Selection(
        [("posted", "Posted Entries Only"), ("all", "Posted + Draft Entries")],
        default="posted", required=True, string="Entries",
    )
    show_opening_balance = fields.Boolean(default=True, string="Show Opening Balance")

    def _create_statement(self):
        self.ensure_one()
        stmt = self.env["customer.statement"].create({
            "partner_id": self.partner_id.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_id": self.company_id.id,
            "journal_ids": [(6, 0, self.journal_ids.ids)],
            "account_ids": [(6, 0, self.account_ids.ids)],
            "move_state": self.move_state,
            "show_opening_balance": self.show_opening_balance,
        })
        stmt.action_get_statement()
        return stmt

    def action_show_statement(self):
        stmt = self._create_statement()
        return {
            "type": "ir.actions.act_window",
            "name": "Customer Statement",
            "res_model": "customer.statement",
            "view_mode": "form",
            "res_id": stmt.id,
            "target": "current",
        }

    def action_print_pdf(self):
        return self._create_statement().action_print_pdf()

    def action_export_excel(self):
        return self._create_statement().action_export_excel()
