from odoo import models, fields
import base64
from io import BytesIO
import xlsxwriter


class VendorStatement(models.Model):
    _name = "vendor.statement"
    _description = "Vendor Statement"
    _rec_name = "partner_id"

    partner_id = fields.Many2one("res.partner", required=True, readonly=True)
    date_from = fields.Date(required=True, readonly=True)
    date_to = fields.Date(required=True, readonly=True)

    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        readonly=True,
    )

    opening_balance = fields.Float(readonly=True)
    line_ids = fields.One2many(
        "vendor.statement.line",
        "statement_id",
        readonly=True,
    )

    # NEW computed "final / last balance" field
    final_balance = fields.Float(readonly=True)

    # ------------------------------------------------------------
    # MAIN STATEMENT GENERATION
    # ------------------------------------------------------------
    def action_get_statement(self):
        mixin = self.env["statement.mixin"]

        # Get opening balance
        self.opening_balance = mixin._get_opening_balance(
            self.partner_id, "liability_payable", self.date_from
        )

        # Build transaction lines with running balance
        lines = mixin._get_statement_lines_with_balance(
            self.partner_id, "liability_payable",
            self.date_from, self.date_to
        )

        # Remove old lines
        self.line_ids.unlink()

        # Insert new lines
        for l in lines:
            self.env["vendor.statement.line"].create({
                "statement_id": self.id,
                "date": l["date"],
                "move": l["move"],
                "reference": l["reference"],
                "due_date": l["due_date"],
                "debit": l["debit"],
                "credit": l["credit"],
                "balance": l["balance"],
            })

        # Update final balance (last balance in list)
        self.final_balance = lines[-1]["balance"] if lines else 0.0

        return True

    # ------------------------------------------------------------
    # PDF EXPORT
    # ------------------------------------------------------------
    def action_print_pdf(self):
        return self.env.ref(
            "account_statement_reports.asr_vendor_statement_report"
        ).report_action(self)

    # ------------------------------------------------------------
    # EXCEL EXPORT
    # ------------------------------------------------------------
    def action_export_excel(self):
        """Generate XLSX vendor statement"""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Vendor Statement")

        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "#,##0.00"})

        # Header
        sheet.write(0, 0, "Vendor:", bold)
        sheet.write(0, 1, self.partner_id.name)

        sheet.write(1, 0, "Period:", bold)
        sheet.write(1, 1, f"{self.date_from or '-'} → {self.date_to or '-'}")

        # Table headers
        headers = ["Date", "Move", "Journal", "Due Date", "Debit", "Credit", "Balance"]
        for col, h in enumerate(headers):
            sheet.write(3, col, h, bold)

        # Lines
        row = 4
        for line in self.line_ids:
            sheet.write(row, 0, str(line.date or ""))
            sheet.write(row, 1, line.move or "")
            sheet.write(row, 2, line.journal or "")
            sheet.write(row, 3, str(line.due_date) if line.due_date else "")
            sheet.write_number(row, 4, line.debit or 0, money)
            sheet.write_number(row, 5, line.credit or 0, money)
            sheet.write_number(row, 6, line.balance or 0, money)
            row += 1

        workbook.close()
        output.seek(0)

        # Attach file to download
        xlsx_data = base64.b64encode(output.read())

        attachment = self.env["ir.attachment"].create({
            "name": f"Vendor Statement - {self.partner_id.name}.xlsx",
            "type": "binary",
            "datas": xlsx_data,
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
