from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class EmployeePortalRedirect(CustomerPortal):

    @http.route(['/my', '/my/home'], type='http', auth='user', website=True)
    def account(self, **kw):
        user = request.env.user
        partner = user.partner_id

        # Vendors first
        if partner.supplier_rank:
            return request.redirect('/vendor/dashboard')

        # Employees second
        if user.employee_id:
            return request.redirect('/my/employee')

        # Customers
        return super().account(**kw)