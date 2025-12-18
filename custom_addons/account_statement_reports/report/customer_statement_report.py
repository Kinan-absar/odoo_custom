# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.tools.misc import formatLang
from datetime import timedelta


class CustomerStatementReport(models.Model):
    _inherit = "account.report"
    
    # ------------------------------------------------------------
    # REPORT METADATA
    # ------------------------------------------------------------
    def _get_report_name(self):
        return _("Customer Statement")

    def _get_report_filters(self):
        return {
            "date": True,
            "journals": True,
            "partners": True,
            "posted_only": True,
        }

    # ------------------------------------------------------------
    # REPORT COLUMNS
    # ------------------------------------------------------------
    def _get_columns(self, options):
        return [
            {"name": _("Date")},
            {"name": _("Move")},
            {"name": _("Reference")},
            {"name": _("Due Date")},
            {"name": _("Debit"), "class": "number"},
            {"name": _("Credit"), "class": "number"},
            {"name": _("Balance"), "class": "number"},
        ]

    # ------------------------------------------------------------
    # MAIN REPORT LINES
    # ------------------------------------------------------------
    def _get_lines(self, options, line_id=None):
        lines = []

        partner_ids = options.get("partner_ids") or []
        date_from = options["date"]["date_from"]
        date_to = options["date"]["date_to"]

        partners = self.env["res.partner"].browse(partner_ids)

        for partner in partners:
            # --------------------------------------------------
            # OPENING BALANCE
            # --------------------------------------------------
            opening_domain = [
                ("partner_id", "=", partner.id),
                ("account_id.account_type", "=", "asset_receivable"),
                ("parent_state", "=", "posted"),
                ("date", "<", date_from),
            ]

            opening_lines = self.env["account.move.line"].search(opening_domain)
            opening_balance = sum(
                (l.debit or 0.0) - (l.credit or 0.0) for l in opening_lines
            )

            running_balance = opening_balance

            # Partner header
            lines.append({
                "id": f"partner_{partner.id}",
                "name": partner.name,
                "level": 1,
                "unfoldable": True,
                "unfolded": True,
                "columns": [{}] * 7,
            })

            # Opening balance row
            lines.append({
                "id": f"opening_{partner.id}",
                "parent_id": f"partner_{partner.id}",
                "level": 2,
                "columns": [
                    {"name": (date_from - timedelta(days=1)).strftime("%Y-%m-%d")},
                    {"name": _("Opening Balance")},
                    {},
                    {},
                    {},
                    {},
                    {
                        "name": formatLang(
                            self.env,
                            opening_balance,
                            currency_obj=partner.company_id.currency_id,
                        )
                    },
                ],
            })

            # --------------------------------------------------
            # TRANSACTIONS
            # --------------------------------------------------
            domain = [
                ("partner_id", "=", partner.id),
                ("account_id.account_type", "=", "asset_receivable"),
                ("parent_state", "=", "posted"),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
            ]

            aml = self.env["account.move.line"].search(domain, order="date, id")

            for line in aml:
                debit = line.debit or 0.0
                credit = line.credit or 0.0
                running_balance += debit - credit

                move = line.move_id

                # YOUR RULE:
                # ONLY customer invoice → payment_reference
                # EVERYTHING else → ref
                if move.move_type == "out_invoice":
                    reference = move.payment_reference or ""
                else:
                    reference = move.ref or ""

                lines.append({
                    "id": f"line_{line.id}",
                    "parent_id": f"partner_{partner.id}",
                    "level": 2,
                    "columns": [
                        {"name": line.date.strftime("%Y-%m-%d") if line.date else ""},
                        {"name": move.name or ""},
                        {"name": reference},
                        {
                            "name": line.date_maturity.strftime("%Y-%m-%d")
                            if line.date_maturity
                            else ""
                        },
                        {
                            "name": formatLang(
                                self.env,
                                debit,
                                currency_obj=partner.company_id.currency_id,
                            )
                        },
                        {
                            "name": formatLang(
                                self.env,
                                credit,
                                currency_obj=partner.company_id.currency_id,
                            )
                        },
                        {
                            "name": formatLang(
                                self.env,
                                running_balance,
                                currency_obj=partner.company_id.currency_id,
                            )
                        },
                    ],
                })

            # --------------------------------------------------
            # TOTAL LINE
            # --------------------------------------------------
            lines.append({
                "id": f"total_{partner.id}",
                "parent_id": f"partner_{partner.id}",
                "level": 2,
                "class": "total",
                "columns": [
                    {},
                    {},
                    {},
                    {},
                    {},
                    {},
                    {
                        "name": formatLang(
                            self.env,
                            running_balance,
                            currency_obj=partner.company_id.currency_id,
                        )
                    },
                ],
            })

        return lines
