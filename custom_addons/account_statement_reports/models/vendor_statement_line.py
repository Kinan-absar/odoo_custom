from odoo import models, fields


class VendorStatementLine(models.Model):
    _name = "vendor.statement.line"
    _description = "Vendor Statement Line"
    _order = "date"

    statement_id = fields.Many2one(
        "vendor.statement",
        ondelete="cascade",
        required=True,
        readonly=True,
    )

    date = fields.Date()
    move = fields.Char()
    reference = fields.Char()
    due_date = fields.Date()
    debit = fields.Float()
    credit = fields.Float()
    balance = fields.Float()
