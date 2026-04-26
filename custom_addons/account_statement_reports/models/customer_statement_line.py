from odoo import models, fields


class CustomerStatementLine(models.Model):
    _name = "customer.statement.line"
    _description = "Customer Statement Line"
    _order = "date, id"

    statement_id = fields.Many2one(
        "customer.statement",
        ondelete="cascade",
        required=True,
    )

    date = fields.Date()
    move = fields.Char()
    reference = fields.Char()
    due_date = fields.Date()

    debit = fields.Float()
    credit = fields.Float()
    balance = fields.Float()
