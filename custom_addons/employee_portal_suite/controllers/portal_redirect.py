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
    Catches ALL /my/signature* routes that Odoo's sign module registers,
    and redirects employees to their employee sign page.

    Odoo 18 navigates to /my/signatures (plural, the list) after signing.
    We cover both the list route and the single-item route just in case.
    """

    @http.route(
        [
            '/my/signatures',
            '/my/signatures/page/<int:page>',
            '/my/signature',
            '/my/signature/<int:request_item_id>',
        ],
        type='http',
        auth='user',
        website=True,
        sitemap=False,
    )
    def employee_sign_done_redirect(self, request_item_id=None, page=None, **kw):
        if request.env.user.employee_id:
            return request.redirect('/my/employee/sign')

        # Non-employee: hand off to the real Sign controller
        from odoo.addons.sign.controllers.main import Sign
        sign_ctrl = Sign()
        try:
            if request_item_id is not None:
                return sign_ctrl.sign_portal_my_request(
                    request_item_id=request_item_id, **kw
                )
            else:
                return sign_ctrl.portal_my_signatures(page=page or 1, **kw)
        except Exception:
            return request.redirect('/my')
