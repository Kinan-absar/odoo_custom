from odoo import api, fields, models
from odoo.exceptions import ValidationError
import base64
from io import BytesIO
import xlsxwriter


class VendorStatement(models.Model):
    _name = "vendor.statement"
    _description = "Vendor Statement"
    _rec_name = "partner_id"

    partner_id = fields.Many2one("res.partner", required=True)
    date_from = fields.Date()
    date_to = fields.Date()
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    journal_ids = fields.Many2many("account.journal", "vendor_statement_journal_rel", "statement_id", "journal_id")
    account_ids = fields.Many2many("account.account", "vendor_statement_account_rel", "statement_id", "account_id")
    move_state = fields.Selection(
        [("posted", "Posted Entries Only"), ("all", "Posted + Draft Entries")],
        default="posted",
        required=True,
    )
    show_opening_balance = fields.Boolean(default=True)
    opening_balance = fields.Float(readonly=True)
    line_ids = fields.One2many("vendor.statement.line", "statement_id", readonly=True)
    final_balance = fields.Float(readonly=True)
    line_count = fields.Integer(string="Transactions", compute="_compute_line_count")

    @api.depends("line_ids")
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids.filtered(lambda l: l.move_id))

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for record in self:
            record.journal_ids = [(5, 0, 0)]
            record.account_ids = [(5, 0, 0)]

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise ValidationError("Date From cannot be later than Date To.")

    def action_get_statement(self):
        for record in self:
            mixin = self.env["statement.mixin"]
            record.opening_balance = mixin._get_opening_balance(
                record.partner_id, "liability_payable", record.date_from, record.company_id,
                record.journal_ids.ids, record.account_ids.ids, record.move_state,
            )
            lines = mixin._get_statement_lines_with_balance(
                record.partner_id, "liability_payable", record.date_from, record.date_to, record.company_id,
                record.journal_ids.ids, record.account_ids.ids, record.move_state, record.show_opening_balance,
            )
            record.line_ids.unlink()
            for line in lines:
                self.env["vendor.statement.line"].create({
                    "statement_id": record.id,
                    "date": line["date"],
                    "move": line["move"],
                    "move_id": line.get("move_id") or False,
                    "reference": line["reference"],
                    "due_date": line["due_date"],
                    "debit": line["debit"],
                    "credit": line["credit"],
                    "balance": line["balance"],
                })
            record.final_balance = lines[-1]["balance"] if lines else record.opening_balance
        return True

    def action_refresh_statement(self):
        self.action_get_statement()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("account_statement_reports.asr_vendor_statement_report").report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Vendor Statement")
        title = workbook.add_format({"bold": True, "font_size": 14})
        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "#,##0.00"})
        header = workbook.add_format({"bold": True, "bg_color": "#EDEDED", "border": 1})

        sheet.write(0, 0, "Vendor Statement", title)
        sheet.write(2, 0, "Vendor:", bold); sheet.write(2, 1, self.partner_id.display_name)
        sheet.write(3, 0, "Company:", bold); sheet.write(3, 1, self.company_id.display_name)
        sheet.write(4, 0, "Period:", bold); sheet.write(4, 1, f"{self.date_from or '-'} -> {self.date_to or '-'}")
        if self.journal_ids:
            sheet.write(5, 0, "Journals:", bold); sheet.write(5, 1, ", ".join(self.journal_ids.mapped("display_name")))
        if self.account_ids:
            sheet.write(6, 0, "Accounts:", bold); sheet.write(6, 1, ", ".join(self.account_ids.mapped("display_name")))

        headers = ["Date", "Move", "Reference", "Due Date", "Debit", "Credit", "Balance"]
        start_row = 8
        for col, label in enumerate(headers):
            sheet.write(start_row, col, label, header)
        row = start_row + 1
        for line in self.line_ids:
            sheet.write(row, 0, str(line.date or "")); sheet.write(row, 1, line.move or "")
            sheet.write(row, 2, line.reference or ""); sheet.write(row, 3, str(line.due_date or ""))
            sheet.write_number(row, 4, line.debit or 0, money); sheet.write_number(row, 5, line.credit or 0, money)
            sheet.write_number(row, 6, line.balance or 0, money); row += 1
        sheet.write(row + 1, 5, "Final Balance", bold); sheet.write_number(row + 1, 6, self.final_balance or 0, money)
        sheet.set_column(0, 0, 12); sheet.set_column(1, 3, 22); sheet.set_column(4, 6, 14)
        workbook.close(); output.seek(0)
        attachment = self.env["ir.attachment"].create({
            "name": f"Vendor Statement - {self.partner_id.name}.xlsx", "type": "binary",
            "datas": base64.b64encode(output.read()), "res_model": self._name, "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url", "url": f"/web/content/{attachment.id}?download=true", "target": "self"}
