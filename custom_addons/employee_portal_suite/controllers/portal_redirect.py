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


class EmployeePortalSignRedirect(http.Controller):
    """
    Intercepts Odoo's post-signing redirect to /my/signature (with or without
    a trailing /<id>) and sends employees to their sign documents page instead.

    In Odoo 18 the sign widget redirects the browser to:
        /my/signature/<request_item_id>?access_token=...
    after the user completes signing. We catch both the bare path and the
    path-with-id variant so nothing slips through.
    """

    @http.route(
        ['/my/signature', '/my/signature/<int:request_item_id>'],
        type='http',
        auth='user',
        website=True,
        sitemap=False,
    )
    def employee_sign_done_redirect(self, request_item_id=None, **kw):
        if request.env.user.employee_id:
            return request.redirect('/my/employee/sign')

        # Non-employee portal user — hand off to the original Sign controller
        # by calling it directly rather than via super() (avoids method-name
        # mismatch across Odoo versions).
        from odoo.addons.sign.controllers.main import Sign
        sign_ctrl = Sign()
        if request_item_id is not None:
            return sign_ctrl.sign_portal_my_request(
                request_item_id=request_item_id, **kw
            )
        # Bare /my/signature with no id — just send them home
        return request.redirect('/my')
