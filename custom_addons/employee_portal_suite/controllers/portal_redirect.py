from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.web.controllers.home import Home


class EmployeePortalLogin(Home):

    def _login_redirect(self, uid, redirect=None):
        """Hook called by Odoo 18 after successful login to determine redirect target."""
        if redirect:
            return redirect
        user = request.env['res.users'].sudo().browse(uid)
        if user.employee_id:
            return '/my/employee'
        return super()._login_redirect(uid, redirect=redirect)


class EmployeePortalRedirect(CustomerPortal):

    @http.route(['/my'], type='http', auth='user', website=True)
    def account(self, **kw):
        if request.env.user.employee_id:
            return request.redirect('/my/employee')
        return super().account(**kw)

    @http.route(['/my/home'], type='http', auth='user', website=True)
    def home_redirect(self, **kw):
        if request.env.user.employee_id:
            return request.redirect('/my/employee')
        return super().account(**kw)
