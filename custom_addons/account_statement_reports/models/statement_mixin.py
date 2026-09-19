# -*- coding: utf-8 -*-
from odoo import models, fields
from datetime import timedelta


class StatementMixin(models.AbstractModel):
    _name = "statement.mixin"
    _description = "Common Statement Logic"

    def _base_domain(self, partner, account_type, company, journal_ids=None, account_ids=None, move_state="posted"):
        domain = [
            ("partner_id", "=", partner.id),
            ("account_id.account_type", "=", account_type),
            ("company_id", "=", company.id),
        ]
        if move_state == "posted":
            domain.append(("parent_state", "=", "posted"))
        if journal_ids:
            domain.append(("journal_id", "in", journal_ids))
        if account_ids:
            domain.append(("account_id", "in", account_ids))
        return domain

    def _get_opening_balance(self, partner, account_type, date_from, company, journal_ids=None, account_ids=None, move_state="posted"):
        if not date_from:
            return 0.0
        domain = self._base_domain(partner, account_type, company, journal_ids, account_ids, move_state)
        domain.append(("date", "<", date_from))
        aml = self.env["account.move.line"].search(domain)
        return sum((l.debit or 0.0) - (l.credit or 0.0) for l in aml)

    def _get_statement_lines_with_balance(
        self, partner, account_type, date_from, date_to, company,
        journal_ids=None, account_ids=None, move_state="posted", show_opening_balance=True,
    ):
        opening_balance = self._get_opening_balance(
            partner, account_type, date_from, company, journal_ids, account_ids, move_state
        )
        domain = self._base_domain(partner, account_type, company, journal_ids, account_ids, move_state)
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))
        aml = self.env["account.move.line"].search(domain, order="date asc, id asc")

        running_balance = opening_balance
        results = []
        if show_opening_balance:
            fake_date = fields.Date.to_date(date_from) - timedelta(days=1) if date_from else None
            results.append({
                "date": fake_date, "move": "Opening Balance", "move_id": False,
                "reference": "", "due_date": None,
                "debit": opening_balance if opening_balance > 0 else 0.0,
                "credit": -opening_balance if opening_balance < 0 else 0.0,
                "balance": opening_balance,
            })

        for line in aml:
            debit = line.debit or 0.0
            credit = line.credit or 0.0
            running_balance += debit - credit
            move = line.move_id
            if move.move_type == "out_invoice":
                reference = move.payment_reference or ""
            else:
                reference = move.ref or ""
            results.append({
                "date": line.date, "move": move.name, "move_id": move.id,
                "reference": reference, "due_date": line.date_maturity,
                "debit": debit, "credit": credit, "balance": running_balance,
            })
        return results

    def _compute_totals(self, lines):
        return {"total_due": 0.0, "total_overdue": 0.0}
