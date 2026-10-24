import base64
import json
import logging
from urllib.parse import quote_plus
from odoo import http, _
from odoo.http import request, content_disposition
from odoo.exceptions import AccessError, UserError, ValidationError
from werkzeug.exceptions import Forbidden, NotFound
from ..models.service import KINDS, PREFIX

_logger = logging.getLogger(__name__)
BASE = '/my/employee/accounting'


class PortalAccounting(http.Controller):
    def _service(self):
        if not request.env.user.share:
            raise Forbidden(_('Internal users must use the Accounting application.'))
        service = request.env['absar.portal.accounting.service']
        try:
            service._actor()
        except AccessError as exc:
            raise Forbidden(str(exc))
        return service

    def _values(self, service, company, **values):
        user, roles = service._actor()
        return dict(company=company, companies=user.sudo().company_ids, roles=roles, kinds=KINDS,
                    configured=bool(company.portal_accounting_journal_ids), quote_plus=quote_plus, **values)

    @http.route(BASE, type='http', auth='user', website=True, methods=['GET'])
    def home(self, company_id=None, **kw):
        if not request.env.user.share:
            return request.redirect('/odoo')
        service = self._service()
        company = service._company(company_id)
        counts = {kind: service._env(company)[spec[0]].search_count(service._domain(company, kind)) for kind, spec in KINDS.items()}
        return request.render(PREFIX + 'home', self._values(service, company, counts=counts))

    @http.route(BASE + '/<string:kind>', type='http', auth='user', website=True, methods=['GET'])
    def listing(self, kind, company_id=None, q='', status='', page=1, **kw):
        if not request.env.user.share:
            return request.redirect('/odoo')
        service = self._service()
        company = service._company(company_id)
        try:
            result = service._list(company, kind, q, status, page)
        except (AccessError, ValueError):
            raise NotFound()
        return request.render(PREFIX + 'listing', self._values(service, company, kind=kind, title=KINDS[kind][1],
            q=q, status=status, message=str(kw.get('message') or '')[:1000], **result))

    @http.route(BASE + '/planned/submit-selected', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def submit_selected(self, company_id=None, **post):
        service = self._service()
        company = service._company(company_id)
        try:
            with request.env.cr.savepoint():
                ids = request.httprequest.form.getlist('record_id')
                count = service._submit_selected(company, [{'id': rid, 'version': post.get('version_' + rid)} for rid in ids])
                message = _('%s planned payments submitted to CEO.') % count
        except (AccessError, UserError, ValidationError) as exc:
            message = str(exc)
        return request.redirect(BASE + '/planned?company_id=%s&message=%s' % (company.id, quote_plus(message)))

    @http.route([BASE + '/<string:kind>/new', BASE + '/<string:kind>/<int:record_id>'],
                type='http', auth='user', website=True, methods=['GET'])
    def detail(self, kind, record_id=None, company_id=None, **kw):
        if not request.env.user.share:
            return request.redirect('/odoo')
        service = self._service()
        company = service._company(company_id)
        try:
            if not record_id:
                service._actor('preparer')
            data = service._detail(company, kind, record_id)
            if not record_id and kind == 'bills' and kw.get('mr_id'):
                data = service._mr_bill_draft(company, kw['mr_id'], data)
            if not record_id and kind == 'payments' and kw.get('bill_id'):
                bill = service._record(company, 'bills', kw['bill_id'])
                if bill.state != 'posted' or bill.amount_residual <= 0:
                    raise UserError(_('Choose a posted bill with an outstanding balance.'))
                payable = bill.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')[:1].account_id
                amount = bill.currency_id._convert(bill.amount_residual, company.currency_id, company, data['date'])
                data.update(partner_id=bill.partner_id.id, account_id=payable.id, amount=amount, bill_ids=bill.ids,
                            description=bill.ref or bill.name)
                data['selections'].update(partner_id={'id':bill.partner_id.id,'name':bill.partner_id.display_name},
                    account_id={'id':payable.id,'name':payable.display_name}, bill_ids=[{'id':bill.id,'name':bill.name}])
        except AccessError:
            raise NotFound()
        return request.render(PREFIX + 'detail', self._values(service, company, kind=kind, title=KINDS[kind][1],
            boot_json=json.dumps(data).replace('<', '\\u003c')))

    @http.route(BASE + '/api/<string:operation>', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def api(self, operation, **post):
        service = self._service()
        try:
            if request.httprequest.content_length and request.httprequest.content_length > 2_000_000:
                raise ValidationError(_('Request is too large.'))
            data = json.loads(post.get('payload') or '{}')
            if not isinstance(data, dict):
                raise ValidationError(_('Invalid request.'))
            with request.env.cr.savepoint():
                company = service._company(data.get('company_id'))
                kind = data.get('kind', 'bills')
                service._kind(kind)
                if operation == 'options':
                    result = service._options(company, data.get('resource'), data.get('q', ''), kind, data.get('partner_id'), data.get('offset',0), data.get('limit',30))
                elif operation in ('product-defaults', 'product-read', 'product-create', 'product-update'):
                    result = service._product_operation(company, kind, operation, data)
                elif operation == 'defaults':
                    result = service._defaults(company,kind,data.get('partner_id'))
                elif operation == 'save':
                    result = service._save(company, kind, data)
                elif operation == 'action':
                    result = service._act(company, kind, data.get('id'), data.get('action'), data)
                elif operation == 'preview':
                    result = service._preview(company, kind, data)
                elif operation == 'po-lines':
                    result = service._po_lines(company, data.get('po_id'))
                else:
                    raise AccessError(_('Unsupported operation.'))
            return request.make_json_response({'ok': True, 'result': result})
        except (AccessError, UserError, ValidationError, ValueError, TypeError) as exc:
            return request.make_json_response({'ok': False, 'error': str(exc)}, status=400)
        except Exception:
            _logger.exception('Portal accounting request failed: %s', operation)
            return request.make_json_response({'ok': False, 'error': _('Operation failed. Nothing was saved. Check the server log for details.')}, status=500)

    @http.route(BASE + '/<string:kind>/<int:record_id>/attachments', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def upload(self, kind, record_id, company_id=None, version=None, **post):
        service = self._service()
        company = service._company(company_id)
        try:
            service._actor('preparer')
            with request.env.cr.savepoint():
                record = service._record(company, kind, record_id)
                record._portal_accounting_lock(version)
                if not service._detail(company, kind, record_id)['editable']:
                    raise AccessError(_('Attachments can only be added to an editable draft.'))
                upload = request.httprequest.files.get('file')
                if not upload or not upload.filename:
                    raise ValidationError(_('Choose a file.'))
                blob = upload.read(15_000_001)
                if len(blob) > 15_000_000:
                    raise ValidationError(_('Maximum attachment size is 15 MB.'))
                attachment = service._env(company)['ir.attachment'].create({
                    'name': upload.filename.rsplit('/', 1)[-1][:200], 'type': 'binary',
                    'datas': base64.b64encode(blob), 'res_model': record._name, 'res_id': record.id,
                    'company_id': company.id, 'public': False})
                service._audit(record, 'Attached supporting document', attachment.name)
            return request.redirect(BASE + '/%s/%s?company_id=%s' % (kind, record_id, company.id))
        except (AccessError, UserError, ValidationError) as exc:
            return request.make_response(str(exc), status=400)

    @http.route(BASE + '/<string:kind>/<int:record_id>/attachment/<int:attachment_id>',
                type='http', auth='user', website=True, methods=['GET'])
    def download(self, kind, record_id, attachment_id, company_id=None, **kw):
        service = self._service()
        company = service._company(company_id)
        record = service._record(company, kind, record_id)
        attachment = service._env(company)['ir.attachment'].search([
            ('id', '=', attachment_id), ('res_model', '=', record._name), ('res_id', '=', record.id), ('type', '=', 'binary')], limit=1)
        if not attachment:
            raise NotFound()
        return request.make_response(base64.b64decode(attachment.datas or b''), headers=[
            ('Content-Type', 'application/octet-stream'), ('Content-Disposition', content_disposition(attachment.name)),
            ('X-Content-Type-Options', 'nosniff')])

    @http.route(BASE + '/<string:kind>/<int:record_id>/print', type='http', auth='user', website=True, methods=['GET'])
    def print_record(self, kind, record_id, company_id=None, journal_entry=None, **kw):
        service = self._service()
        company = service._company(company_id)
        record = service._record(company, kind, record_id)
        if journal_entry == '1':
            if kind not in ('bills','refunds','journals','payments','receipts'):
                raise NotFound()
            if record._name != 'account.move':
                record = record.move_id
                if not record:
                    raise UserError(_('Post the voucher before printing its journal entry.'))
            report = 'wm_journal_entry_report.account_journal'
        elif kind in ('bills', 'refunds'):
            report = 'account.account_invoices'
        elif kind == 'journals':
            report = 'wm_journal_entry_report.account_journal'
        elif kind == 'payments':
            report = 'internal_transfer_voucher.action_payment_voucher_pdf'
        elif kind == 'receipts':
            report = 'internal_transfer_voucher.action_receipt_voucher_pdf'
        else:
            raise NotFound()
        if report == 'wm_journal_entry_report.account_journal':
            action = request.env.ref(report, raise_if_not_found=False)
            # The bill/voucher was authorized above. Portal users cannot read
            # report action metadata; inspect only this fixed server-side action.
            if action:
                action = action.sudo()
            if not action or action._name != 'ir.actions.report' or action.model != 'account.move':
                raise UserError(_('The existing Print JV report (wm_journal_entry_report) must be installed to print journal entries.'))
        pdf, _format = service._env(company)['ir.actions.report']._render_qweb_pdf(report, res_ids=record.ids)
        return request.make_response(pdf, headers=[('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition('%s.pdf' % (record.name or 'Document')))])
