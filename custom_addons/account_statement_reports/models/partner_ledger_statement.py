# -*- coding: utf-8 -*-
import base64
from io import BytesIO

import xlsxwriter

from odoo import _, fields, models
from odoo.exceptions import UserError


class PartnerStatementExport(models.TransientModel):
    _name = "partner.statement.export"
    _description = "Partner Ledger Statement Export"

    partner_id = fields.Many2one("res.partner", required=True, readonly=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True)
    date_from = fields.Date(readonly=True)
    date_to = fields.Date(readonly=True)
    account_type = fields.Selection(
        [("both", "Receivable & Payable"), ("receivable", "Receivable"), ("payable", "Payable")],
        default="both",
        readonly=True,
    )
    move_state = fields.Selection(
        [("posted", "Posted Entries Only"), ("all", "Posted + Draft Entries")],
        default="posted",
        readonly=True,
    )
    unreconciled = fields.Boolean(readonly=True)
    show_opening_balance = fields.Boolean(default=True, readonly=True)
    journal_ids = fields.Many2many("account.journal", readonly=True)
    line_ids = fields.One2many("partner.statement.export.line", "statement_id", readonly=True)
    opening_balance = fields.Monetary(currency_field="currency_id", readonly=True)
    final_balance = fields.Monetary(currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    def _account_types(self):
        self.ensure_one()
        if self.account_type == "receivable":
            return ["asset_receivable"]
        if self.account_type == "payable":
            return ["liability_payable"]
        return ["asset_receivable", "liability_payable"]

    def _base_domain(self):
        self.ensure_one()
        domain = [
            ("partner_id", "=", self.partner_id.id),
            ("company_id", "=", self.company_id.id),
            ("account_id.account_type", "in", self._account_types()),
        ]
        if self.move_state == "posted":
            domain.append(("parent_state", "=", "posted"))
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.unreconciled:
            domain.append(("reconciled", "=", False))
        return domain

    def action_compute(self):
        for record in self:
            base_domain = record._base_domain()
            opening = 0.0
            if record.date_from:
                opening_lines = self.env["account.move.line"].search(base_domain + [("date", "<", record.date_from)])
                opening = sum(line.debit - line.credit for line in opening_lines)
            record.opening_balance = opening

            domain = list(base_domain)
            if record.date_from:
                domain.append(("date", ">=", record.date_from))
            if record.date_to:
                domain.append(("date", "<=", record.date_to))
            amls = self.env["account.move.line"].search(domain, order="date asc, id asc")

            record.line_ids.unlink()
            running = opening
            commands = []
            for aml in amls:
                running += aml.debit - aml.credit
                move = aml.move_id
                reference = move.payment_reference if move.move_type == "out_invoice" else move.ref
                commands.append((0, 0, {
                    "date": aml.date,
                    "move_id": move.id,
                    "move_name": move.name,
                    "reference": reference or "",
                    "due_date": aml.date_maturity,
                    "debit": aml.debit,
                    "credit": aml.credit,
                    "balance": running,
                }))
            record.line_ids = commands
            record.final_balance = running
        return True

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("account_statement_reports.asr_partner_ledger_statement_report").report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Account Statement")
        title = workbook.add_format({"bold": True, "font_size": 15})
        bold = workbook.add_format({"bold": True})
        header = workbook.add_format({"bold": True, "bg_color": "#EDEDED", "border": 1})
        money = workbook.add_format({"num_format": "#,##0.00"})

        sheet.write(0, 0, "Account Statement", title)
        sheet.write(2, 0, "Partner", bold); sheet.write(2, 1, self.partner_id.display_name)
        sheet.write(3, 0, "Company", bold); sheet.write(3, 1, self.company_id.display_name)
        sheet.write(4, 0, "Period", bold); sheet.write(4, 1, f"{self.date_from or '-'} -> {self.date_to or '-'}")
        sheet.write(5, 0, "Account Type", bold); sheet.write(5, 1, dict(self._fields['account_type'].selection).get(self.account_type))
        sheet.write(6, 0, "Entries", bold); sheet.write(6, 1, dict(self._fields['move_state'].selection).get(self.move_state))
        if self.journal_ids:
            sheet.write(7, 0, "Journals", bold); sheet.write(7, 1, ", ".join(self.journal_ids.mapped("display_name")))
        sheet.write(8, 0, "Opening Balance", bold); sheet.write_number(8, 1, self.opening_balance or 0.0, money)

        headers = ["Date", "Journal Entry", "Reference", "Due Date", "Debit", "Credit", "Balance"]
        start_row = 10
        for col, label in enumerate(headers):
            sheet.write(start_row, col, label, header)
        row = start_row + 1
        for line in self.line_ids:
            sheet.write(row, 0, str(line.date or ""))
            sheet.write(row, 1, line.move_name or "")
            sheet.write(row, 2, line.reference or "")
            sheet.write(row, 3, str(line.due_date or ""))
            sheet.write_number(row, 4, line.debit or 0.0, money)
            sheet.write_number(row, 5, line.credit or 0.0, money)
            sheet.write_number(row, 6, line.balance or 0.0, money)
            row += 1
        sheet.write(row + 1, 5, "Final Balance", bold)
        sheet.write_number(row + 1, 6, self.final_balance or 0.0, money)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 3, 24)
        sheet.set_column(4, 6, 15)
        workbook.close()
        output.seek(0)

        attachment = self.env["ir.attachment"].create({
            "name": f"Account Statement - {self.partner_id.name}.xlsx",
            "type": "binary",
            "datas": base64.b64encode(output.read()),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }


class PartnerStatementExportLine(models.TransientModel):
    _name = "partner.statement.export.line"
    _description = "Partner Ledger Statement Export Line"
    _order = "date, id"

    statement_id = fields.Many2one("partner.statement.export", required=True, ondelete="cascade")
    date = fields.Date(readonly=True)
    move_id = fields.Many2one("account.move", readonly=True)
    move_name = fields.Char(readonly=True)
    reference = fields.Char(readonly=True)
    due_date = fields.Date(readonly=True)
    debit = fields.Monetary(currency_field="currency_id", readonly=True)
    credit = fields.Monetary(currency_field="currency_id", readonly=True)
    balance = fields.Monetary(currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one(related="statement_id.currency_id", readonly=True)


class AccountPartnerLedgerReportHandler(models.AbstractModel):
    _inherit = "account.partner.ledger.report.handler"

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(report, options, previous_options)

        # This handler is also inherited by Follow-up Reports. Add the buttons only
        # on the real Partner Ledger handler, never on its subclasses.
        if self._name != "account.partner.ledger.report.handler":
            return

        buttons = options.setdefault("buttons", [])
        if not any(button.get("action") == "action_asr_statement_pdf" for button in buttons):
            buttons.extend([
                {
                    "name": _("Statement PDF"),
                    "action": "action_asr_statement_pdf",
                    "sequence": 80,
                    "always_show": True,
                },
                {
                    "name": _("Statement Excel"),
                    "action": "action_asr_statement_excel",
                    "sequence": 81,
                    "always_show": True,
                },
            ])

    def _asr_selected_company(self, options):
        company_ids = []
        for company in options.get("companies", []) or []:
            if isinstance(company, dict) and company.get("selected") and company.get("id"):
                company_ids.append(int(company["id"]))
        if len(company_ids) == 1:
            return self.env["res.company"].browse(company_ids[0])
        return self.env.company

    def _asr_selected_journal_ids(self, options):
        journal_ids = []
        for journal in options.get("journals", []) or []:
            if isinstance(journal, dict) and journal.get("selected") and journal.get("id"):
                journal_ids.append(int(journal["id"]))
        return journal_ids

    def _asr_account_type(self, options):
        value = options.get("account_type") or options.get("filter_account_type")
        if isinstance(value, str) and value in {"both", "receivable", "payable"}:
            return value
        if isinstance(value, list):
            selected = []
            for item in value:
                if isinstance(item, dict) and item.get("selected"):
                    key = item.get("id") or item.get("value") or item.get("key")
                    if key in {"receivable", "payable"}:
                        selected.append(key)
            if len(selected) == 1:
                return selected[0]
        # Partner Ledger's standard "Trade Partners" option means both.
        return "both"

    def _asr_prepare_statement(self, options):
        partner_ids = [int(pid) for pid in (options.get("partner_ids") or [])]
        if len(partner_ids) != 1:
            raise UserError(_("Select exactly one partner in the Partner Ledger 'Partners' filter before exporting a statement."))

        date_options = options.get("date") or {}
        date_from = date_options.get("date_from")
        date_to = date_options.get("date_to")
        company = self._asr_selected_company(options)

        vals = {
            "partner_id": partner_ids[0],
            "company_id": company.id,
            "date_from": date_from or False,
            "date_to": date_to or False,
            "account_type": self._asr_account_type(options),
            "move_state": "all" if options.get("all_entries") else "posted",
            "unreconciled": bool(options.get("unreconciled")),
            "show_opening_balance": True,
            "journal_ids": [(6, 0, self._asr_selected_journal_ids(options))],
        }
        statement = self.env["partner.statement.export"].create(vals)
        statement.action_compute()
        return statement

    def action_asr_statement_pdf(self, options):
        return self._asr_prepare_statement(options).action_print_pdf()

    def action_asr_statement_excel(self, options):
        return self._asr_prepare_statement(options).action_export_excel()
