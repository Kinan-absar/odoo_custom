"""Company-scoped ER/MR administration without granting portal backend ACLs."""
import base64
import math
from urllib.parse import urlencode

from markupsafe import Markup
from odoo import http, _
from odoo.http import request, content_disposition
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression
from werkzeug.exceptions import Forbidden, NotFound

from .portal_prepare import integer, PREFIX

CONTROL = '/my/employee/purchase/request-control'
MODELS = {'er': 'employee.request', 'mr': 'material.request'}
ADMIN_GROUPS = ('employee_portal_suite.group_employee_portal_admin',
                'employee_portal_suite.group_employee_portal_superadmin')


def company_domain(company_id):
    # Project company wins; requests without a project company use employee company.
    return ['|', ('project_id.company_id', '=', company_id), '&',
            ('project_id.company_id', '=', False), ('employee_id.company_id', '=', company_id)]


class PortalRequestControl(http.Controller):
    def _actor(self):
        user = request.env.user
        if (not user.active or user._is_public()
                or user.has_group('employee_portal_suite.group_attendance_only')
                or not any(user.has_group(group) for group in ADMIN_GROUPS)):
            raise Forbidden()
        return user

    def _company(self, value=None):
        user = self._actor()
        company = request.env['res.company'].sudo().browse(integer(value, user.company_id.id)).exists()
        if not company or company not in user.company_ids:
            raise NotFound()
        return company

    def _model(self, kind, company):
        if kind not in MODELS:
            raise NotFound()
        return request.env[MODELS[kind]].sudo().with_context(
            allowed_company_ids=[company.id], force_company=company.id).with_company(company)

    def _record(self, kind, ident, company):
        record = self._model(kind, company).search(expression.AND([
            company_domain(company.id), [('id', '=', integer(ident))]]), limit=1)
        if not record:
            raise NotFound()
        return record

    def _lock(self, record, version):
        table = 'material_request' if record._name == 'material.request' else 'employee_request'
        request.env.cr.execute('SELECT id FROM ' + table + ' WHERE id=%s FOR UPDATE', [record.id])
        record.invalidate_recordset()
        if not version or str(record.write_date) != version:
            raise ValidationError(_('This request changed. Reload it before continuing.'))

    def _url(self, kind, ident=None, **params):
        path = CONTROL + '/' + kind + ('/' + str(ident) if ident else '')
        return path + ('?' + urlencode(params) if params else '')

    def _selections(self, record, name):
        return dict(record._fields[name]._description_selection(record.env))

    def _row(self, kind, rec, company):
        states = self._selections(rec, 'state')
        pending = rec.current_approval_line_id.name if rec.state == 'workflow' else states.get(rec.state, rec.state)
        if kind == 'mr' and rec.needs_clarification:
            pending = rec.display_state or _('Clarification Requested')
        return dict(id=rec.id, name=rec.name, employee=rec.employee_id.name,
                    project=rec.project_id.display_name or '—', date=rec.request_date,
                    state=rec.state, status=states.get(rec.state, rec.state), pending=pending or '—',
                    url=self._url(kind, rec.id, company_id=company.id),
                    category=rec.get_request_type_display() if kind == 'er' else
                    (_('No PO Required') if rec.no_po_required else _('PO Required')),
                    followup=self._selections(rec, 'accounting_docs_status').get(rec.accounting_docs_status, '') if kind == 'mr' else '')

    @http.route([CONTROL, CONTROL + '/<string:kind>'], type='http', auth='user', website=True, methods=['GET'])
    def listing(self, kind='mr', **kw):
        company = self._company(kw.get('company_id'))
        model = self._model(kind, company)
        domain = company_domain(company.id)
        q = str(kw.get('q') or '').strip()[:120]
        status = str(kw.get('status') or '')
        followup = str(kw.get('followup') or '') if kind == 'mr' else ''
        states = self._selections(model, 'state')
        counts = {key: model.search_count(expression.AND([domain, extra])) for key, extra in {
            'all': [], 'pending': [('state', 'not in', ['draft', 'returned', 'approved', 'rejected'])],
            'approved': [('state', '=', 'approved')],
            'returned': [('state', '=', 'returned')],
        }.items()}
        if status == 'pending':
            domain = expression.AND([domain, [('state', 'not in', ['draft', 'returned', 'approved', 'rejected'])]])
        elif status in states:
            domain = expression.AND([domain, [('state', '=', status)]])
        elif status:
            raise NotFound()
        if kind == 'mr':
            filters = {'po': [('state', '=', 'approved'), ('no_po_required', '=', False), ('purchase_order_ids', '=', False)],
                       'bill': [('state', '=', 'approved'), ('no_po_required', '=', True), ('purchase_order_ids', '=', False), ('vendor_bill_ids', '=', False)],
                       'clarification': [('needs_clarification', '=', True)],
                       'accounting': [('accounting_docs_status', 'in', ['submitted', 'need_more'])]}
            if followup:
                if followup not in filters:
                    raise NotFound()
                domain = expression.AND([domain, filters[followup]])
        if q:
            names = ['name', 'employee_id.name', 'project_id.name'] + (['line_ids.item_name'] if kind == 'mr' else ['description'])
            domain = expression.AND([domain, expression.OR([[(name, 'ilike', q)] for name in names])])
        count = model.search_count(domain)
        pages = max(1, math.ceil(count / 25))
        page = min(max(integer(kw.get('page'), 1), 1), pages)
        params = dict(company_id=company.id, q=q, status=status, followup=followup)
        records = model.search(domain, order='id desc', limit=25, offset=(page-1)*25)
        return request.render(PREFIX + 'request_control_list', dict(
            company=company, companies=request.env.user.company_ids, kind=kind, base=CONTROL,
            rows=[self._row(kind, rec, company) for rec in records], counts=counts,
            q=q, status=status, followup=followup, states=states, total=count, page=page, pages=pages,
            previous_url=self._url(kind, page=page-1, **params), next_url=self._url(kind, page=page+1, **params)))

    def _links(self, rec, company):
        from .portal_prepare import PortalPurchasePrepare
        links = []
        for po in rec.purchase_order_ids.filtered(lambda p: p.company_id == company):
            url = ''
            if not request.env.user.share:
                url = '/odoo/purchase.order/%s' % po.id
            else:
                try:
                    PortalPurchasePrepare()._record(po.id)
                    url = '/my/employee/purchase/%s' % po.id
                except (AccessError, Forbidden, NotFound):
                    pass
            links.append(dict(name=po.name, status=po.state, url=url, kind='PO'))
        bills = request.env['account.move'].sudo().with_company(company).search([
            ('company_id', '=', company.id), ('move_type', '=', 'in_invoice'), '|',
            ('material_request_id', '=', rec.id), ('invoice_line_ids.purchase_line_id.order_id', 'in', rec.purchase_order_ids.ids)])
        for bill in bills:
            url = ''
            if not request.env.user.share:
                url = '/odoo/account.move/%s' % bill.id
            elif 'absar.portal.accounting.service' in request.env:
                try:
                    service = request.env['absar.portal.accounting.service']
                    service._actor()
                    service._record(service._company(company.id), 'bills', bill.id)
                    url = '/my/employee/accounting/bills/%s?company_id=%s' % (bill.id, company.id)
                except (AccessError, UserError, NotFound):
                    pass
            links.append(dict(name=bill.name or bill.ref or _('Draft Bill'), status=bill.state, url=url, kind='Vendor Bill'))
        return links

    @http.route(CONTROL + '/<string:kind>/<int:ident>', type='http', auth='user', website=True, methods=['GET'])
    def detail(self, kind, ident, **kw):
        company = self._company(kw.get('company_id'))
        rec = self._record(kind, ident, company)
        user = request.env.user
        attachments = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', rec._name), ('res_id', '=', rec.id), ('type', '=', 'binary'),
            '|', ('company_id', '=', False), ('company_id', '=', company.id)])
        before = max(integer(kw.get('before'), 0), 0)
        message_domain = [('model', '=', rec._name), ('res_id', '=', rec.id),
                          ('message_type', 'in', ['comment', 'notification']), ('is_internal', '=', False),
                          ('subtype_id', '!=', False), ('subtype_id.internal', '=', False)]
        if before:
            message_domain.append(('id', '<', before))
        messages = request.env['mail.message'].sudo().search(message_domain, order='id desc', limit=51)
        can_bill = False
        if kind == 'mr' and user.share and 'absar.portal.accounting.service' in request.env:
            try:
                service = request.env['absar.portal.accounting.service']
                service._actor('preparer')
                can_bill = bool(service._company(company.id).portal_accounting_journal_ids)
            except AccessError:
                pass
        fields_to_show = ['description', 'leave_from', 'leave_to', 'time_off_type_id', 'time_off_id'] if kind == 'er' else [
            'worksite', 'delivery_date', 'purpose', 'notes', 'quotation_status', 'accounting_docs_status',
            'docs_submitted_by', 'docs_submitted_date', 'accounting_docs_note', 'needs_clarification',
            'clarification_question', 'clarification_reply', 'clarification_requested_by']
        details = []
        for name in fields_to_show:
            if name not in rec._fields:
                continue
            field = rec._fields[name]
            value = rec[name]
            if field.type == 'many2one':
                value = value.display_name or ''
            elif field.type == 'selection':
                value = self._selections(rec, name).get(value, '')
            elif field.type == 'boolean':
                value = _('Yes') if value else _('No')
            if value:
                details.append((field.string, value))
        accounts = request.env['account.account'].sudo().search([
            ('company_ids', 'in', [company.id]), ('deprecated', '=', False),
            ('account_type', 'in', ['expense', 'expense_direct_cost'])], order='code,id') if kind == 'mr' else []
        return request.render(PREFIX + 'request_control_detail', dict(
            base=CONTROL, kind=kind, company=company, rec=rec, row=self._row(kind, rec, company), details=details,
            version=str(rec.write_date), attachments=attachments, messages=messages[:50],
            older_url=self._url(kind, rec.id, company_id=company.id, before=messages[49].id) if len(messages)>50 else '',
            timeline=rec.get_portal_timeline(), links=self._links(rec, company) if kind == 'mr' else [],
            can_approve=rec._portal_can_approve(user), can_clarify=kind == 'mr' and rec._can_toggle_clarification(),
            can_po=user.has_group(PREFIX+'group_portal_purchase_preparer'),
            can_bill=can_bill, accounts=accounts,
            docs_states=self._selections(rec, 'accounting_docs_status') if kind == 'mr' else {},
            error='', notice=str(kw.get('notice') or '')[:500], back_url=self._url(kind, company_id=company.id)))

    @http.route(CONTROL + '/<string:kind>/<int:ident>/action', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def action(self, kind, ident, **post):
        company = self._company(post.get('company_id'))
        rec = self._record(kind, ident, company)
        user = request.env.user
        try:
            with request.env.cr.savepoint():
                self._lock(rec, post.get('version'))
                operation = post.get('operation')
                comment = str(post.get('comment') or '').strip()[:10000]
                if operation == 'comment':
                    if not comment:
                        raise ValidationError(_('Write a message before sending.'))
                    rec.message_post(body=Markup('<p style="white-space:pre-wrap">%s</p>') % comment,
                        message_type='comment', subtype_xmlid='mail.mt_comment', author_id=user.partner_id.id,
                        partner_ids=rec.employee_id.user_id.partner_id.ids)
                elif operation == 'followup' and kind == 'mr':
                    if rec.state != 'approved':
                        raise UserError(_('Procurement settings can only be changed after approval.'))
                    no_po = post.get('no_po_required') == '1'
                    if no_po and rec.purchase_order_ids:
                        raise UserError(_('This MR already has a PO. Create its bills through the PO flow.'))
                    if not no_po and rec.vendor_bill_ids:
                        raise UserError(_('This MR already has direct vendor bills. Keep No PO Required.'))
                    status = post.get('accounting_docs_status')
                    if status not in self._selections(rec, 'accounting_docs_status'):
                        raise ValidationError(_('Invalid accounting document status.'))
                    account = request.env['account.account'].sudo().search([
                        ('id', '=', integer(post.get('expense_account_id'))), ('company_ids', 'in', [company.id]),
                        ('deprecated', '=', False), ('account_type', 'in', ['expense', 'expense_direct_cost'])], limit=1)
                    if post.get('expense_account_id') and not account:
                        raise ValidationError(_('Choose an expense account from this company.'))
                    rec.write(dict(no_po_required=no_po, expense_account_id=account.id or False,
                        accounting_docs_status=status, accounting_docs_note=str(post.get('accounting_docs_note') or '')[:10000]))
                elif operation == 'clarify' and kind == 'mr':
                    rec._request_clarification(comment)
                elif operation in ('approve', 'reject', 'return'):
                    if not rec._portal_can_approve(user):
                        raise AccessError(_('You are not an eligible approver for the current step.'))
                    if operation != 'approve' and not comment:
                        raise ValidationError(_('Enter a reason.'))
                    if operation == 'return':
                        if rec.state != 'workflow':
                            raise UserError(_('Return for correction is available for configurable workflows.'))
                        rec.with_context(workflow_actor_user_id=user.id)._workflow_return_confirm(comment)
                    elif rec.state == 'workflow':
                        rec.current_approval_line_id.comment = comment or False
                        if operation == 'approve':
                            rec.with_context(workflow_actor_user_id=user.id).action_workflow_approve()
                        else:
                            rec.with_context(workflow_actor_user_id=user.id).action_workflow_reject()
                    else:
                        methods = ({'manager':'action_manager_approve','hr':'action_hr_approve','finance':'action_finance_approve','ceo':'action_ceo_approve'}
                            if kind == 'er' else {'purchase':'action_purchase','store':'action_store','project_manager':'action_project_manager','director':'action_director','ceo':'action_ceo'})
                        if rec.state not in methods:
                            raise UserError(_('No approval is pending.'))
                        rec.write({rec.state+'_comment':comment or False})
                        if operation == 'reject':
                            rec.action_reject()
                        else:
                            getattr(rec, methods[rec.state])()
                else:
                    raise ValidationError(_('Unsupported request action.'))
                # Comments must invalidate the snapshot too, protecting repeated clicks.
                if operation == 'comment':
                    from odoo import fields
                    rec.write({'write_date': fields.Datetime.now()})
                notice = _('Changes saved.')
        except (AccessError, UserError, ValidationError) as exc:
            notice = str(exc)
        return request.redirect(self._url(kind, ident, company_id=company.id, notice=notice))

    @http.route(CONTROL + '/<string:kind>/<int:ident>/print', type='http', auth='user', methods=['GET'])
    def print_request(self, kind, ident, **kw):
        company = self._company(kw.get('company_id'))
        rec = self._record(kind, ident, company)
        report = 'employee_portal_suite.' + ('material_request_pdf' if kind == 'mr' else 'employee_request_pdf')
        pdf, _format = request.env['ir.actions.report'].sudo().with_company(company)._render_qweb_pdf(report, res_ids=[rec.id])
        return request.make_response(pdf, headers=[('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(rec.name + '.pdf')), ('Cache-Control', 'private, no-store')])

    @http.route(CONTROL + '/<string:kind>/<int:ident>/attachment/<int:attachment_id>', type='http', auth='user', methods=['GET'])
    def attachment(self, kind, ident, attachment_id, **kw):
        company = self._company(kw.get('company_id'))
        rec = self._record(kind, ident, company)
        attachment = request.env['ir.attachment'].sudo().search([
            ('id', '=', attachment_id), ('res_model', '=', rec._name), ('res_id', '=', rec.id), ('type', '=', 'binary'),
            '|', ('company_id', '=', False), ('company_id', '=', company.id)], limit=1)
        if not attachment:
            raise NotFound()
        return request.make_response(base64.b64decode(attachment.datas or b''), headers=[
            ('Content-Type', 'application/octet-stream'), ('Content-Disposition', content_disposition(attachment.name)),
            ('X-Content-Type-Options', 'nosniff'), ('Cache-Control', 'private, no-store')])
