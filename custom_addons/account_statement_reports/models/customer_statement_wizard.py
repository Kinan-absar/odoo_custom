from odoo import models, fields


class CustomerStatementWizard(models.TransientModel):
    _name = "customer.statement.wizard"
    _description = "Customer Statement Wizard"

    partner_id = fields.Many2one("res.partner", required=True)
    date_from = fields.Date()
    date_to = fields.Date()

    # ------------------------------------------------------------
    # INTERNAL: Create the real statement record
    # ------------------------------------------------------------
    def _create_statement(self):
        stmt = self.env["customer.statement"].create({
            "partner_id": self.partner_id.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_id": self.env.company.id,
        })
        stmt.action_get_statement()
        return stmt

    # ------------------------------------------------------------
    # SHOW BUTTON
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # PDF BUTTON
    # ------------------------------------------------------------
    def action_print_pdf(self):
        stmt = self._create_statement()
        return stmt.action_print_pdf()
