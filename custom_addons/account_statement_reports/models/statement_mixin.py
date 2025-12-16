# -*- coding: utf-8 -*-
from odoo import models, fields
from datetime import timedelta


class StatementMixin(models.AbstractModel):
    _name = "statement.mixin"
    _description = "Common Statement Logic"

    # ------------------------------------------------------
    # OPENING BALANCE
    # ------------------------------------------------------
    def _get_opening_balance(self, partner, account_type, date_from):
        """Compute balance before the chosen start date."""
        if not date_from:
            return 0.0

        aml = self.env["account.move.line"].search([
            ("partner_id", "=", partner.id),
            ("account_id.account_type", "=", account_type),
            ("parent_state", "=", "posted"),
            ("date", "<", date_from),
        ])

        return sum((l.debit or 0.0) - (l.credit or 0.0) for l in aml)

    # ------------------------------------------------------
    # BUILD STATEMENT WITH RUNNING BALANCE
    # ------------------------------------------------------
    def _get_statement_lines_with_balance(self, partner, account_type, date_from, date_to):
        """Returns full list of statement rows including running balance."""
        opening_balance = self._get_opening_balance(partner, account_type, date_from)

        # Query lines inside date range
        domain = [
            ("partner_id", "=", partner.id),
            ("account_id.account_type", "=", account_type),
            ("parent_state", "=", "posted"),
        ]
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))

        aml = self.env["account.move.line"].search(domain, order="date asc, id asc")

        running_balance = opening_balance
        results = []

        # ------------------------------------------------------
        # OPENING BALANCE ROW (fake date ensures top position)
        # ------------------------------------------------------
        if date_from:
            fake_date = fields.Date.to_date(date_from) - timedelta(days=1)
        else:
            fake_date = None

        results.append({
            "date": fake_date,
            "move": "Opening Balance",
            "reference": "",
            "due_date": None,
            "debit": opening_balance if opening_balance > 0 else 0.0,
            "credit": -opening_balance if opening_balance < 0 else 0.0,
            "balance": opening_balance,
        })

        # ------------------------------------------------------
        # NORMAL TRANSACTION LINES
        # ------------------------------------------------------
        for line in aml:
            debit = line.debit or 0.0
            credit = line.credit or 0.0
            running_balance += (debit - credit)

            move = line.move_id

            # -----------------------------------------
            # Reference logic (FINAL & SIMPLE)
            # -----------------------------------------
            if move.move_type in ("in_payment", "out_payment"):
                # Any payment → use journal entry reference
                reference = move.ref or ""
            else:
                # Invoice / Bill
                if account_type == "asset_receivable":
                    # Customer invoice
                    reference = move.payment_reference or ""
                else:
                    # Vendor bill
                    reference = move.ref or ""

            results.append({
                "date": line.date,
                "move": move.name,
                "reference": reference,
                "due_date": line.date_maturity,
                "debit": debit,
                "credit": credit,
                "balance": running_balance,
            })

        return results



    # ------------------------------------------------------
    # TOTALS (we don't use them in UI, but kept for compatibility)
    # ------------------------------------------------------
    def _compute_totals(self, lines):
        return {"total_due": 0.0, "total_overdue": 0.0}
