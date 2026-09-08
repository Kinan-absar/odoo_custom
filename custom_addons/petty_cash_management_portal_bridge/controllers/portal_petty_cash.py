from odoo import http, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from werkzeug.exceptions import NotFound
import base64
from markupsafe import Markup


def _petty_status_badge(rec):
    if rec.state == "approved":
        return Markup('<span class="badge bg-success">Approved</span>')
    if rec.state == "refused":
        return Markup('<span class="badge bg-danger">Rejected</span>')
    if rec.state == "submitted":
        return Markup('<span class="badge bg-warning text-dark">Submitted</span>')
    if rec.state == "draft":
        return Markup('<span class="badge bg-light text-dark border">Draft</span>')
    return Markup('<span class="badge bg-secondary">Unknown</span>')


class PortalPettyCash(CustomerPortal):

    def _is_portal_approver(self):
        return request.env.user.has_group(
            'petty_cash_management.group_portal_petty_cash_approver'
        )

    def _get_report_for_view(self, report_id, allow_owner=True, allow_approver=True):
        report = request.env['petty.cash'].sudo().browse(report_id).exists()
        if not report:
            return False

        is_owner = report.user_id.id == request.env.user.id
        is_approver = self._is_portal_approver()

        if allow_owner and is_owner:
            return report
        if allow_approver and is_approver and report.state != 'draft':
            return report
        return False

    # -------------------------------
    # MY REPORTS
    # -------------------------------
    @http.route(['/my/employee/petty-cash'], type='http', auth="user", website=True)
    def portal_my_petty_cash(self, **kwargs):
        reports = request.env['petty.cash'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ])

        return request.render(
            'petty_cash_management_portal_bridge.portal_petty_cash_list',
            {
                'reports': reports,
                'page_name': 'petty_cash',
                'status_badge': _petty_status_badge,
            }
        )

    # -------------------------------
    # APPROVAL QUEUE
    # -------------------------------
    @http.route(['/my/employee/petty-cash/approvals'], type='http', auth='user', website=True)
    def portal_petty_cash_approvals(self, status='submitted', **kwargs):
        if not self._is_portal_approver():
            return request.redirect('/my')

        allowed_statuses = {'submitted', 'approved', 'refused', 'all'}
        if status not in allowed_statuses:
            status = 'submitted'

        domain = [('state', '!=', 'draft')]
        if status != 'all':
            domain.append(('state', '=', status))

        reports = request.env['petty.cash'].sudo().search(domain, order='id desc')
        pending_count = request.env['petty.cash'].sudo().search_count([('state', '=', 'submitted')])

        return request.render(
            'petty_cash_management_portal_bridge.portal_petty_cash_approvals',
            {
                'reports': reports,
                'status': status,
                'pending_count': pending_count,
                'page_name': 'petty_cash_approvals',
                'status_badge': _petty_status_badge,
            }
        )

    # -------------------------------
    # DETAIL
    # -------------------------------
    @http.route(['/my/employee/petty-cash/<int:report_id>'], type='http', auth="user", website=True)
    def portal_petty_cash_detail(self, report_id, **kwargs):
        report = self._get_report_for_view(report_id)
        if not report:
            return request.redirect('/my')

        is_owner = report.user_id.id == request.env.user.id
        is_approver_view = self._is_portal_approver() and not is_owner

        categories = request.env['petty.cash.category'].sudo().search([]) if is_owner and report.state == 'draft' else request.env['petty.cash.category']

        return request.render(
            'petty_cash_management_portal_bridge.portal_petty_cash_detail',
            {
                'report': report,
                'categories': categories,
                'status_badge': _petty_status_badge,
                'is_owner': is_owner,
                'is_approver_view': is_approver_view,
                'can_approve': self._is_portal_approver() and report.state == 'submitted',
                'back_url': '/my/employee/petty-cash' if is_owner else '/my/employee/petty-cash/approvals',
            }
        )

    # -------------------------------
    # CREATE REPORT
    # -------------------------------
    @http.route('/my/employee/petty-cash/create', type='http', auth='user', website=True, methods=['POST'])
    def portal_petty_cash_create(self, **post):
        if not request.env.user.has_group('petty_cash_management.group_portal_petty_cash_user'):
            return request.redirect('/my')

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
        return request.redirect(f'/my/employee/petty-cash/{petty_cash.id}')

    # -------------------------------
    # ADD LINE
    # -------------------------------
    @http.route('/my/employee/petty-cash/<int:report_id>/add-line', type='http', auth='user', website=True, methods=['POST'])
    def portal_add_line_post(self, report_id, **post):
        report = self._get_report_for_view(report_id, allow_approver=False)
        if not report:
            return request.redirect('/my')
        if report.state != 'draft':
            return request.redirect('/my/employee/petty-cash/%s' % report_id)

        category_id = post.get('category_id')
        amount = post.get('amount_before_vat')
        if not category_id or not amount:
            return request.redirect('/my/employee/petty-cash/%s' % report_id)

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
            'vat_applicable': bool(post.get('vat_applicable')),
        }
        line = request.env['petty.cash.line'].sudo().create(line_vals)

        attachment = post.get('attachment')
        if attachment:
            att = request.env['ir.attachment'].sudo().create({
                'name': attachment.filename,
                'datas': base64.b64encode(attachment.read()),
                'res_model': 'petty.cash.line',
                'res_id': line.id,
                'public': False,
            })
            line.attachment_ids = [(4, att.id)]

        return request.redirect('/my/employee/petty-cash/%s' % report.id)

    @http.route('/my/employee/petty-cash/<int:report_id>/submit', type='http', auth='user', website=True, methods=['POST'])
    def portal_submit_report(self, report_id, **post):
        report = self._get_report_for_view(report_id, allow_approver=False)
        if not report:
            return request.redirect('/my')
        if not report.line_ids:
            return request.redirect(f'/my/employee/petty-cash/{report_id}?error=no_lines')
        if report.state != 'draft':
            return request.redirect(f'/my/employee/petty-cash/{report_id}')

        report.with_user(request.env.user).action_submit()
        return request.redirect(f'/my/employee/petty-cash/{report_id}')

    @http.route('/my/employee/petty-cash/<int:report_id>/upload-attachment', type='http', auth='user', website=True, methods=['POST'])
    def portal_upload_attachment(self, report_id, **post):
        report = self._get_report_for_view(report_id, allow_approver=False)
        if not report:
            return request.redirect('/my')
        if report.state != 'draft':
            return request.redirect(f'/my/employee/petty-cash/{report_id}')

        file = post.get('attachment')
        if file:
            attachment = request.env['ir.attachment'].sudo().create({
                'name': file.filename,
                'datas': base64.b64encode(file.read()),
                'res_model': 'petty.cash',
                'res_id': report.id,
                'public': False,
            })
            report.attachment_ids = [(4, attachment.id)]

        return request.redirect(f'/my/employee/petty-cash/{report_id}?success=uploaded')

    @http.route('/my/employee/petty-cash/attachment/<int:attachment_id>/download', type='http', auth='user', website=True)
    def portal_download_attachment(self, attachment_id, **kw):
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment:
            raise NotFound()

        report = False
        if attachment.res_model == 'petty.cash':
            report = request.env['petty.cash'].sudo().browse(attachment.res_id).exists()
        elif attachment.res_model == 'petty.cash.line':
            line = request.env['petty.cash.line'].sudo().browse(attachment.res_id).exists()
            report = line.petty_cash_id if line else False

        if not report:
            # Also support attachments linked through the report M2M relation.
            report = request.env['petty.cash'].sudo().search([('attachment_ids', 'in', attachment.id)], limit=1)

        if not report or not self._get_report_for_view(report.id):
            raise NotFound()

        raw = base64.b64decode(attachment.datas or b'')
        headers = [
            ('Content-Type', attachment.mimetype or 'application/octet-stream'),
            ('Content-Length', str(len(raw))),
            ('Content-Disposition', 'inline; filename="%s"' % (attachment.name or 'attachment')),
        ]
        return request.make_response(raw, headers=headers)

    @http.route('/my/employee/petty-cash/attachment/<int:attachment_id>/delete', type='http', auth='user', website=True, methods=['POST'])
    def portal_delete_attachment(self, attachment_id, **kw):
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment or attachment.res_model != 'petty.cash':
            return request.redirect('/my')

        report = self._get_report_for_view(attachment.res_id, allow_approver=False)
        if not report:
            return request.redirect('/my')
        if report.state != 'draft':
            return request.redirect(f'/my/employee/petty-cash/{report.id}')

        attachment.unlink()
        return request.redirect(f'/my/employee/petty-cash/{report.id}')

    # -------------------------------
    # APPROVE / REJECT
    # -------------------------------
    @http.route('/my/employee/petty-cash/<int:report_id>/approve', type='http', auth='user', website=True, methods=['POST'])
    def portal_approve_report(self, report_id, **post):
        if not self._is_portal_approver():
            return request.redirect('/my')

        report = self._get_report_for_view(report_id, allow_owner=False, allow_approver=True)
        if not report or report.state != 'submitted':
            return request.redirect('/my/employee/petty-cash/approvals')

        request.env['petty.cash'].browse(report.id).action_portal_approve()
        return request.redirect(f'/my/employee/petty-cash/{report.id}?decision=approved')

    @http.route('/my/employee/petty-cash/<int:report_id>/reject', type='http', auth='user', website=True, methods=['POST'])
    def portal_reject_report(self, report_id, **post):
        if not self._is_portal_approver():
            return request.redirect('/my')

        report = self._get_report_for_view(report_id, allow_owner=False, allow_approver=True)
        if not report or report.state != 'submitted':
            return request.redirect('/my/employee/petty-cash/approvals')

        request.env['petty.cash'].browse(report.id).action_portal_refuse()
        return request.redirect(f'/my/employee/petty-cash/{report.id}?decision=rejected')

    @http.route(['/my/employee/petty-cash/<int:report_id>/print'], type='http', auth='user', website=True)
    def portal_print_petty_cash_report(self, report_id, **kwargs):
        report = self._get_report_for_view(report_id)
        if not report:
            return request.redirect('/my')

        pdf, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'petty_cash_management.petty_cash_report_action',
            res_ids=report.ids
        )
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', str(len(pdf))),
            ('Content-Disposition', 'attachment; filename="%s.pdf"' % (report.name or 'Petty Cash Report')),
        ]
        return request.make_response(pdf, headers=headers)
