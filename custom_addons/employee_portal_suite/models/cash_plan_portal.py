from odoo import api, fields, models


class CashPlan(models.Model):
    _inherit = "cash.plan"

    portal_variance_inflow = fields.Monetary(
        string="Inflow Variance",
        currency_field="currency_id",
        compute="_compute_portal_variances",
    )
    portal_variance_outflow = fields.Monetary(
        string="Outflow Variance",
        currency_field="currency_id",
        compute="_compute_portal_variances",
    )
    portal_variance_net = fields.Monetary(
        string="Net Cash Variance",
        currency_field="currency_id",
        compute="_compute_portal_variances",
    )

    @api.depends(
        "forecast_inflow",
        "actual_inflow",
        "forecast_outflow",
        "actual_outflow",
        "forecast_net",
        "actual_net",
    )
    def _compute_portal_variances(self):
        for record in self:
            record.portal_variance_inflow = record.actual_inflow - record.forecast_inflow
            record.portal_variance_outflow = record.actual_outflow - record.forecast_outflow
            record.portal_variance_net = record.actual_net - record.forecast_net
