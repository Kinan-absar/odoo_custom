from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class PortalPettyCash(CustomerPortal):

    @http.route(['/my/petty-cash'], type='http', auth="user", website=True)
    def portal_my_petty_cash(self, **kwargs):
        reports = request.env['petty.cash'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ])

        values = {
            'reports': reports,
            'page_name': 'petty_cash',
        }
        return request.render(
            'petty_cash_management.portal_petty_cash_list',
            values
        )

    @http.route(['/my/petty-cash/<int:report_id>'], type='http', auth="user", website=True)
    def portal_petty_cash_detail(self, report_id, **kwargs):
        report = request.env['petty.cash'].sudo().browse(report_id)

        if report.user_id != request.env.user:
            return request.redirect('/my')

        values = {
            'report': report,
            'page_name': 'petty_cash_detail',
        }
        return request.render(
            'petty_cash_management.portal_petty_cash_detail',
            values
        )
