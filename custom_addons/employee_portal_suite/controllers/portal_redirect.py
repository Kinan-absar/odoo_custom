from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.web.controllers.home import Home


class EmployeePortalLogin(Home):

    @http.route('/web/login', type='http', auth='none', website=True, sitemap=False)
    def web_login(self, redirect=None, **kw):
        response = super().web_login(redirect=redirect, **kw)
        # Only act after a successful login POST
        if request.httprequest.method == 'POST' and request.session.uid:
            user = request.env['res.users'].sudo().browse(request.session.uid)
            if user.employee_id:
                return request.redirect('/my/employee')
        return response


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
