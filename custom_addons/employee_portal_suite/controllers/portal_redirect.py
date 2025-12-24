from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class EmployeePortalRedirect(CustomerPortal):

    @http.route(['/my'], type='http', auth='user', website=True)
    def account(self, **kw):
        """Redirect employees away from customer portal."""
        user = request.env.user

        # Employees → always redirect to employee portal
        if user.employee_id:
            return request.redirect('/my/employee')

        # Customers/vendors → normal Odoo portal
        return super().account(**kw)


    @http.route(['/my/home'], type='http', auth='user', website=True)
    def home_redirect(self, **kw):
        """Override My Account page. Employees should never land here."""
        user = request.env.user

        # Employees → force employee dashboard
        if user.employee_id:
            return request.redirect('/my/employee')

        # Normal customers/vendors → default portal home
        return super().account(**kw)
    
