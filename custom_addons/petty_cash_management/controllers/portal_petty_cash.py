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
from odoo import http
from odoo.http import request

class PettyCashPortal(http.Controller):

    @http.route('/my/petty-cash/new', type='http', auth='user', website=True)
    def portal_petty_cash_new(self, **kw):

        return request.render(
            'petty_cash_management.portal_petty_cash_form',
            {}
        )
    @http.route('/my/petty-cash/create', type='http', auth='user', website=True, methods=['POST'])
    def portal_petty_cash_create(self, **post):

        petty_cash = request.env['petty.cash'].sudo().create({
            'user_id': request.env.user.id,
            'date': post.get('date'),
        })

        return request.redirect(f'/my/petty-cash/{petty_cash.id}')
    @http.route('/my/petty-cash/<int:report_id>', type='http', auth='user', website=True)
    def portal_petty_cash_detail(self, report_id, **kw):

        report = request.env['petty.cash'].sudo().browse(report_id)

        if report.user_id.id != request.env.user.id:
            return request.redirect('/my')

        return request.render(
            'petty_cash_management.portal_petty_cash_detail',
            {'report': report}
        )
