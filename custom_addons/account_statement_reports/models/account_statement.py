# -*- coding: utf-8 -*-
import base64
from datetime import date
from io import BytesIO

import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from .statement_mixin import EMPLOYEE_ACCOUNT_TYPES


class AccountStatement(models.Model):
    _name = "account.statement"
    _description = "Account Statement"
    _rec_name = "name"
    _order = "id desc"

    name = fields.Char(default="Account Statements", required=True)

    statement_type = fields.Selection(
        [("receivable", "Customer"), ("payable", "Vendor"), ("employee", "Employee")],
        string="Statement Type",
        required=True,
        default="receivable",
    )
    partner_id = fields.Many2one("res.partner", string="Partner")
    date_from = fields.Date(string="Date From")
    date_to = fields.Date(string="Date To")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    journal_ids = fields.Many2many(
        "account.journal", "account_statement_journal_rel", "statement_id", "journal_id", string="Journals"
    )
    account_ids = fields.Many2many(
        "account.account", "account_statement_account_rel", "statement_id", "account_id", string="Accounts"
    )
    move_state = fields.Selection(
        [("posted", "Posted Entries Only"), ("all", "Posted + Draft Entries")],
        string="Entries",
        default="posted",
        required=True,
    )
    show_opening_balance = fields.Boolean(string="Opening Balance", default=True)

    opening_balance = fields.Monetary(currency_field="currency_id", readonly=True)
    final_balance = fields.Monetary(currency_field="currency_id", readonly=True)
    total_debit = fields.Monetary(currency_field="currency_id", readonly=True)
    total_credit = fields.Monetary(currency_field="currency_id", readonly=True)
    line_count = fields.Integer(string="Transactions", readonly=True)
    line_ids = fields.One2many("account.statement.line", "statement_id", readonly=True)

    @api.model
    def _default_period(self):
        today = fields.Date.context_today(self)
        return today.replace(day=1), today

    @api.model
    def action_open_new_workspace(self):
        date_from, date_to = self._default_period()
        record = self.create({
            "statement_type": self.env.context.get("default_statement_type", "receivable"),
            "partner_id": self.env.context.get("default_partner_id") or False,
            "company_id": self.env.context.get("default_company_id") or self.env.company.id,
            "date_from": self.env.context.get("default_date_from") or date_from,
            "date_to": self.env.context.get("default_date_to") or date_to,
        })
        if record.partner_id:
            record.action_apply_filters()
        return {
            "type": "ir.actions.act_window",
            "name": "Account Statements",
            "res_model": "account.statement",
            "view_mode": "form",
            "res_id": record.id,
            "target": "current",
            "views": [(self.env.ref("account_statement_reports.account_statement_workspace_form").id, "form")],
        }

    @api.onchange("statement_type")
    def _onchange_statement_type(self):
        date_from, date_to = self._default_period()
        self.partner_id = False
        self.date_from = date_from
        self.date_to = date_to
        self.journal_ids = [(5, 0, 0)]
        self.account_ids = [(5, 0, 0)]
        self.move_state = 'posted'
        self.show_opening_balance = True
        self.line_ids = [(5, 0, 0)]
        self._clear_results()

    @api.onchange("company_id")
    def _onchange_company_id(self):
        self.journal_ids = [(5, 0, 0)]
        self.account_ids = [(5, 0, 0)]
        self._clear_results()

    def _clear_results(self):
        for record in self:
            record.opening_balance = 0.0
            record.final_balance = 0.0
            record.total_debit = 0.0
            record.total_credit = 0.0
            record.line_count = 0

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise ValidationError("Date From cannot be later than Date To.")

    def _account_type(self):
        self.ensure_one()
        return {"receivable": "asset_receivable", "payable": "liability_payable", "employee": "employee"}[self.statement_type]

    def action_apply_filters(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError("Select a customer, vendor or employee partner before applying the statement filters.")

        if self.statement_type == "employee":
            if not self.account_ids:
                raise UserError("Select the employee accounts to include: salary payable, accrued benefits, advances or loans.")
            if self.account_ids.filtered(lambda account: self.company_id not in account.company_ids or account.account_type not in EMPLOYEE_ACCOUNT_TYPES):
                raise UserError("Employee accounts must belong to the selected company and be employee asset/liability accounts. Expense, income and bank/cash accounts are excluded.")
        account_type = self._account_type()
        mixin = self.env["statement.mixin"]
        self.opening_balance = mixin._get_opening_balance(
            self.partner_id,
            account_type,
            self.date_from,
            self.company_id,
            self.journal_ids.ids,
            self.account_ids.ids,
            self.move_state,
        )
        lines = mixin._get_statement_lines_with_balance(
            self.partner_id,
            account_type,
            self.date_from,
            self.date_to,
            self.company_id,
            self.journal_ids.ids,
            self.account_ids.ids,
            self.move_state,
            self.show_opening_balance,
        )

        self.line_ids.unlink()
        vals_list = []
        total_debit = 0.0
        total_credit = 0.0
        transaction_count = 0
        for line in lines:
            vals_list.append({
                "statement_id": self.id,
                "date": line["date"],
                "move": line["move"],
                "move_id": line.get("move_id") or False,
                "account_id": line.get("account_id") or False,
                "description": line.get("description") or "",
                "reference": line["reference"],
                "due_date": line["due_date"],
                "debit": line["debit"],
                "credit": line["credit"],
                "balance": line["balance"],
            })
            # Totals must match the rows currently visible in the statement, including
            # the synthetic opening-balance row when that option is enabled.
            total_debit += line["debit"] or 0.0
            total_credit += line["credit"] or 0.0
            if line.get("move_id"):
                transaction_count += 1
        if vals_list:
            self.env["account.statement.line"].create(vals_list)

        self.line_count = transaction_count
        self.total_debit = total_debit
        self.total_credit = total_credit
        self.final_balance = lines[-1]["balance"] if lines else self.opening_balance
        # Returning False lets the form controller refresh this record in place instead
        # of triggering a full client-page reload.
        return False

    def action_reset_filters(self):
        self.ensure_one()
        date_from, date_to = self._default_period()
        self.write({
            "partner_id": False,
            "date_from": date_from,
            "date_to": date_to,
            "journal_ids": [(5, 0, 0)],
            "account_ids": [(5, 0, 0)],
            "move_state": "posted",
            "show_opening_balance": True,
            "opening_balance": 0.0,
            "final_balance": 0.0,
            "total_debit": 0.0,
            "total_credit": 0.0,
            "line_count": 0,
        })
        self.line_ids.unlink()
        return False

    def action_print_pdf(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError("Select a partner and apply the filters before printing.")
        if self.statement_type == "employee":
            self.action_apply_filters()
        return self.env.ref("account_statement_reports.asr_account_statement_report").report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError("Select a partner and apply the filters before exporting.")

        if self.statement_type == "employee":
            self.action_apply_filters()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False})
        sheet = workbook.add_worksheet("Account Statement")

        title = workbook.add_format({"bold": True, "font_size": 14})
        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "#,##0.00"})
        header = workbook.add_format({"bold": True, "bg_color": "#E9EEF5", "border": 1})
        total_label = workbook.add_format({"bold": True, "bg_color": "#F3F4F6", "top": 1, "bottom": 1, "align": "right"})
        total_money = workbook.add_format({"bold": True, "bg_color": "#F3F4F6", "top": 1, "bottom": 1, "num_format": "#,##0.00"})

        type_label = dict(self._fields["statement_type"].selection)[self.statement_type]
        sheet.write(0, 0, "Account Statement", title)
        sheet.write(2, 0, "Type:", bold); sheet.write(2, 1, type_label)
        sheet.write(3, 0, "Partner:", bold); sheet.write(3, 1, self.partner_id.display_name)
        sheet.write(4, 0, "Company:", bold); sheet.write(4, 1, self.company_id.display_name)
        sheet.write(5, 0, "Period:", bold); sheet.write(5, 1, f"{self.date_from or '-'} -> {self.date_to or '-'}")
        if self.journal_ids:
            sheet.write(6, 0, "Journals:", bold); sheet.write(6, 1, ", ".join(self.journal_ids.mapped("display_name")))
        if self.account_ids:
            sheet.write(7, 0, "Accounts:", bold); sheet.write(7, 1, ", ".join(self.account_ids.mapped("display_name")))

        headers = ["Date", "Journal Entry", "Reference", "Due Date", "Debit", "Credit", "Balance"]
        employee = self.statement_type == "employee"
        if employee:
            headers = ["Date", "Journal Entry", "Account", "Reference", "Due Date", "Debit", "Credit", "Balance"]
        amount_col = len(headers) - 3
        start_row = 9
        for col, label in enumerate(headers):
            sheet.write(start_row, col, label, header)
        row = start_row + 1
        for line in self.line_ids:
            cells = [str(line.date or ""), line.move or ""]
            if employee:
                cells += [line.account_id.display_name if line.account_id else ""]
            cells += [line.reference or "", str(line.due_date or "")]
            for col, text in enumerate(cells):
                sheet.write(row, col, text)
            sheet.write_number(row, amount_col, line.debit or 0.0, money)
            sheet.write_number(row, amount_col + 1, line.credit or 0.0, money)
            sheet.write_number(row, amount_col + 2, line.balance or 0.0, money)
            row += 1

        # Statement totals directly under the exported transaction rows.
        exported_total_debit = sum(self.line_ids.mapped("debit"))
        exported_total_credit = sum(self.line_ids.mapped("credit"))
        sheet.merge_range(row, 0, row, amount_col - 1, "Totals", total_label)
        sheet.write_number(row, amount_col, exported_total_debit or 0.0, total_money)
        sheet.write_number(row, amount_col + 1, exported_total_credit or 0.0, total_money)
        sheet.write_number(row, amount_col + 2, self.final_balance or 0.0, total_money)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, amount_col - 1, 24)
        sheet.set_column(amount_col, amount_col + 2, 15)
        if employee:
            sheet.write(row + 2, 0, "Balance = debit - credit: positive means due from employee; negative means due to employee.")
        workbook.close()
        output.seek(0)

        safe_name = (self.partner_id.name or "Partner").replace("/", "-")
        attachment = self.env["ir.attachment"].create({
            "name": f"Account Statement - {safe_name}.xlsx",
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
