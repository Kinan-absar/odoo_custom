from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
import base64
from odoo import fields


class PortalPettyCash(CustomerPortal):

    # -------------------------------
    # LIST
    # -------------------------------
    @http.route(['/my/petty-cash'], type='http', auth="user", website=True)
    def portal_my_petty_cash(self, **kwargs):

        reports = request.env['petty.cash'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ])

        return request.render(
            'petty_cash_management.portal_petty_cash_list',
            {
                'reports': reports,
                'page_name': 'petty_cash',
            }
        )

    # -------------------------------
    # DETAIL (WITH CATEGORIES)
    # -------------------------------
    @http.route(['/my/petty-cash/<int:report_id>'], type='http', auth="user", website=True)
    def portal_petty_cash_detail(self, report_id, **kwargs):

        report = request.env['petty.cash'].sudo().browse(report_id)

        if not report or report.user_id != request.env.user:
            return request.redirect('/my')

        categories = request.env['petty.cash.category'].sudo().search([])

        return request.render(
            'petty_cash_management.portal_petty_cash_detail',
            {
                'report': report,
                'categories': categories,   # 🔥 THIS WAS MISSING
            }
        )

    # -------------------------------
    # CREATE REPORT
    # -------------------------------
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
            'date': fields.Date.today(),
        })

        petty_cash = PettyCash.create(vals)

        return request.redirect(f'/my/petty-cash/{petty_cash.id}')

    # -------------------------------
    # ADD LINE (INLINE)
    # -------------------------------
    @http.route('/my/petty-cash/<int:report_id>/add-line',
                type='http', auth='user', website=True, methods=['POST'])
    def portal_add_line_post(self, report_id, **post):

        report = request.env['petty.cash'].sudo().browse(report_id)

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
        
    @http.route('/my/petty-cash/<int:report_id>/submit',
            type='http', auth='user', website=True, methods=['POST'])
    def portal_submit_report(self, report_id, **post):

        report = request.env['petty.cash'].sudo().browse(report_id)

        if not report or report.user_id != request.env.user:
            return request.redirect('/my')

        if not report.line_ids:
            return request.redirect(f'/my/petty-cash/{report_id}?error=no_lines')

        if report.state != 'draft':
            return request.redirect(f'/my/petty-cash/{report_id}')

        report.action_submit()

        return request.redirect(f'/my/petty-cash/{report_id}')

    @http.route('/my/petty-cash/<int:report_id>/upload-attachment',
            type='http', auth='user', website=True, methods=['POST'])
    def portal_upload_attachment(self, report_id, **post):

        report = request.env['petty.cash'].sudo().browse(report_id)

        if not report or report.user_id != request.env.user:
            return request.redirect('/my')

        file = post.get('attachment')

        if file:
            attachment = request.env['ir.attachment'].sudo().create({
                'name': file.filename,
                'datas': base64.b64encode(file.read()),
                'res_model': 'petty.cash',
                'res_id': report.id,
            })

            # 🔥 IMPORTANT
            report.attachment_ids = [(4, attachment.id)]

        return request.redirect(f'/my/petty-cash/{report_id}?success=uploaded')

