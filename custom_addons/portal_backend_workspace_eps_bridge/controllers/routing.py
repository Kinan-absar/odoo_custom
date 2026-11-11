from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal_backend_workspace.controllers.workspace import WorkspaceLogin, WorkspacePortalHome
from odoo.addons.employee_portal_suite.controllers.portal_redirect import EmployeePortalLogin, EmployeePortalRedirect

class WorkspaceEPSLogin(WorkspaceLogin, EmployeePortalLogin):
    def _login_redirect(self, uid, redirect=None):
        # A document/deep link must never be replaced by a home page.
        if redirect and redirect.split('?')[0] not in ('/my', '/my/home', '/'):
            return super()._login_redirect(uid, redirect=redirect)
        user = request.env['res.users'].sudo().browse(uid)
        if user.share:
            if user._pbw_eps_entry_url():
                return user._pbw_eps_entry_url()
            if user._pbw_has_access():
                return '/my/workspace'
        return super()._login_redirect(uid, redirect=redirect)

class WorkspaceEPSHome(WorkspacePortalHome, EmployeePortalRedirect):
    @http.route(['/my', '/my/home'], type='http', auth='user', website=True, methods=['GET'])
    def home(self, **kw):
        user = request.env.user
        if user.share:
            destination = user._pbw_eps_entry_url()
            if destination:
                return request.redirect(destination)
            if user._pbw_has_access():
                return request.redirect('/my/workspace')
        return CustomerPortal.home(self, **kw)

    @http.route(['/my/home'], type='http', auth='user', website=True, methods=['GET'])
    def home_redirect(self, **kw):
        return self.home(**kw)

    @http.route(['/my/account'], type='http', auth='user', website=True)
    def account(self, redirect=None, **post):
        # EPS remapped this inherited method to /my. Restore the native profile route
        # and use home() above as the sole shared default-home policy.
        return CustomerPortal.account(self, redirect=redirect, **post)
