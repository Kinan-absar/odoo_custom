from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Ensure the removed legacy Employee Admin settings view is gone."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    imd = env['ir.model.data'].search([
        ('module', '=', 'portal_backend_workspace'),
        ('name', '=', 'hr__company_employee_admin_report'),
    ], limit=1)
    if imd:
        view = env['ir.ui.view'].browse(imd.res_id).exists()
        if view:
            view.unlink()
        imd.exists().unlink()
