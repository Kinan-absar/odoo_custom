from odoo import fields, models, _
from odoo.exceptions import ValidationError


class ExcelReportWizard(models.TransientModel):
    _name = "excel.report.wizard"
    _description = "Generate Excel Report"

    report_id = fields.Many2one("excel.report.template", required=True, readonly=True)
    report_name = fields.Char(related="report_id.name", readonly=True)
    model_name = fields.Char(related="report_id.model_id.name", readonly=True)
    has_date_filter = fields.Boolean(compute="_compute_has_date_filter")
    date_from = fields.Date()
    date_to = fields.Date()

    def _compute_has_date_filter(self):
        for rec in self:
            rec.has_date_filter = bool(rec.report_id.date_field_id)

    def action_download(self):
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError(_("Date From cannot be later than Date To."))
        return {
            "type": "ir.actions.act_url",
            "url": f"/excel_report_builder/download/{self.id}",
            "target": "self",
        }
