# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountStatementLine(models.Model):
    _name = "account.statement.line"
    _description = "Account Statement Line"
    _order = "date, id"

    statement_id = fields.Many2one("account.statement", required=True, ondelete="cascade", index=True)
    date = fields.Date()
    move = fields.Char(string="Journal Entry")
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True)
    reference = fields.Char()
    due_date = fields.Date(string="Due Date")
    debit = fields.Monetary(currency_field="currency_id")
    credit = fields.Monetary(currency_field="currency_id")
    balance = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(related="statement_id.currency_id", readonly=True)
