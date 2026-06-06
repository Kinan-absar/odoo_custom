from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.web.controllers.home import Home
from odoo.addons.sign.controllers.main import Sign


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


class EmployeePortalSignRedirect(Sign):

    @http.route(['/my/signature'], type='http', auth='user', website=True)
    def portal_my_signature(self, **kw):
        """After finishing signing a document, redirect employees to their
        sign documents page instead of the default Odoo /my/signature page."""
        if request.env.user.employee_id:
            return request.redirect('/my/employee/sign')
        return super().portal_my_signature(**kw)
