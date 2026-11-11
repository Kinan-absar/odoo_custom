from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Compatibility-only field. It is intentionally not exposed in any view.
    # Keep it while upgrading databases that still contain the old Employee
    # Admin settings view; that view is removed by the 18.0.0.9.11 migration.
    pbw_hr_payslip_report_id = fields.Many2one(
        'ir.actions.report',
        string='Legacy Employee Admin Payslip Report',
        help='Legacy compatibility field retained only so older installed views can be removed safely during upgrade.',
    )
