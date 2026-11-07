from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.web.controllers.home import Home

def _has_any_workspace(user):
    return any(user.has_group(g) for g in [
        'portal_backend_workspace.sales__group_portal_sales_user',
        'portal_backend_workspace.sales__group_portal_sales_creator',
        'portal_backend_workspace.purchase__group_portal_purchase_monitor',
        'portal_backend_workspace.purchase__group_portal_purchase_preparer',
        'portal_backend_workspace.accounting__group_accountant',
        'portal_backend_workspace.accounting__group_preparer',
        'portal_backend_workspace.hr__group_employee_admin',
    ])

class WorkspaceHome(http.Controller):
    @http.route('/my/workspace', type='http', auth='user', website=True, methods=['GET'])
    def dashboard(self, **kwargs):
        if not _has_any_workspace(request.env.user):
            return request.redirect('/my')
        return request.render('portal_backend_workspace.pbw_dashboard')

# Do not override /my or login routes: an EPS user retains the EPS homepage.
