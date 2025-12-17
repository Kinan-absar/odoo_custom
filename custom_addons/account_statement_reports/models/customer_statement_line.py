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
    currency_id = fields.Many2one(
            "res.currency",
            related="statement_id.company_id.currency_id",
            store=True,
            readonly=True,
    )
    date = fields.Date()
    move = fields.Char()
    reference = fields.Char()
    due_date = fields.Date()

    debit = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    credit = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    balance = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
