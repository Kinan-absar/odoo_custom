"""Non-invasive landing behavior. EPS takes priority for dual members."""
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.web.controllers.home import Home

GROUP = 'portal_backend_workspace.group_workspace_user'

def workspace_user(user):
    return bool(user and user.share and not user._is_public() and user.has_group(GROUP))

def eps_member(user):
    # No EPS imports, groups or routes are required. Check installation explicitly.
    eps_installed = bool(request.env['ir.module.module'].sudo().search_count([
        ('name', '=', 'employee_portal_suite'), ('state', '=', 'installed')]))
    return bool(eps_installed and user.share and user.employee_id)

class WorkspaceLogin(Home):
    def _login_redirect(self, uid, redirect=None):
        if redirect:
            return super()._login_redirect(uid, redirect=redirect)
        user = request.env['res.users'].sudo().browse(uid)
        if eps_member(user):
            return '/my/employee'
        if workspace_user(user):
            return '/my/workspace'
        return super()._login_redirect(uid, redirect=redirect)

class WorkspaceHome(CustomerPortal):
    @http.route(['/my', '/my/home'], type='http', auth='user', website=True)
    def account(self, **kw):
        user = request.env.user
        if eps_member(user):
            return request.redirect('/my/employee')
        if workspace_user(user):
            return request.redirect('/my/workspace')
        return super().account(**kw)
