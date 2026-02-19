from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
import base64

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

        PettyCash = request.env['petty.cash'].sudo()

        vals = PettyCash.default_get([
            'petty_cash_account_id',
            'input_vat_account_id',
            'journal_id',
            'currency_id',
        ])

        vals.update({
            'user_id': request.env.user.id,
            'date': post.get('date'),
        })

        petty_cash = PettyCash.create(vals)

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
    @http.route('/my/petty-cash/<int:report_id>/add-line',
                type='http', auth='user', website=True)
    def portal_add_line(self, report_id, **kw):

        report = request.env['petty.cash'].sudo().browse(report_id)

        if report.user_id != request.env.user:
            return request.redirect('/my')

        if report.state != 'draft':
            return request.redirect('/my/petty-cash/%s' % report_id)

        categories = request.env['petty.cash.category'].sudo().search([])

        return request.render(
            'petty_cash_management.portal_petty_cash_add_line',
            {
                'report': report,
                'categories': categories,
            }
        )
   @http.route('/my/petty-cash/<int:report_id>/add-line',
                type='http', auth='user', website=True, methods=['POST'])
    def portal_add_line_post(self, report_id, **post):

        report = request.env['petty.cash'].browse(report_id)

        if not report or report.user_id != request.env.user:
            return request.redirect('/my')

        if report.state != 'draft':
            return request.redirect('/my/petty-cash/%s' % report_id)

        category_id = post.get('category_id')
        amount = post.get('amount_before_vat')

        if not category_id or not amount:
            return request.redirect('/my/petty-cash/%s' % report_id)

        line_vals = {
            'petty_cash_id': report.id,
            'date': post.get('date'),
            'supplier': post.get('supplier'),
            'invoice_number': post.get('invoice_number'),
            'po_number': post.get('po_number'),
            'mr_number': post.get('mr_number'),
            'zone': post.get('zone'),
            'description': post.get('description'),
            'category_id': int(category_id),
            'amount_before_vat': float(amount),
            'vat_applicable': True if post.get('vat_applicable') else False,
        }

        line = request.env['petty.cash.line'].sudo().create(line_vals)

        attachment = post.get('attachment')
        if attachment:
            request.env['ir.attachment'].sudo().create({
                'name': attachment.filename,
                'datas': base64.b64encode(attachment.read()),
                'res_model': 'petty.cash.line',
                'res_id': line.id,
            })

        return request.redirect('/my/petty-cash/%s' % report.id)

