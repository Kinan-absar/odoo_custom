import base64
import json
import logging
from urllib.parse import quote_plus
from odoo import http, _
from odoo.http import request, content_disposition
from odoo.exceptions import AccessError, UserError, ValidationError
from werkzeug.exceptions import Forbidden, NotFound
from ...models.accounting.service import KINDS, PREFIX
_logger = logging.getLogger(__name__)
BASE = '/my/workspace/accounting'

class PortalAccounting(http.Controller):

    def _service(self):
        if not request.env.user.share:
            raise Forbidden(_('Internal users must use the Accounting application.'))
        service = request.env['pbw.portal.accounting.service']
        try:
            service._actor()
        except AccessError as exc:
            raise Forbidden(str(exc))
        return service

    def _values(self, service, company, **values):
        values.setdefault('kind', '')
        user, roles = service._actor(kind=values.get('kind'))
        return dict(company=company, companies=user.sudo().company_ids, roles=roles, kinds=service._kinds(), configured=service._workspace_configured(company, values.get('kind')), quote_plus=quote_plus, **values)

    @http.route(BASE, type='http', auth='user', website=True, methods=['GET'])
    def home(self, company_id=None, **kw):
        if not request.env.user.share:
            return request.redirect('/odoo')
        service = self._service()
        company = service._company(company_id)
        counts = {kind: service._env(company)[spec[0]].search_count(service._domain(company, kind)) for kind, spec in service._kinds().items()}
        if request.env.user.has_group('portal_backend_workspace.accounting__group_approver'):
            request.env['pbw.notification.seen']._mark_seen(request.env.uid, 'accounting_approval')
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
        return request.render(PREFIX + 'listing', self._values(service, company, kind=kind, title=KINDS[kind][1], q=q, status=status, message=str(kw.get('message') or '')[:1000], **result))

    @http.route([BASE + '/<string:kind>/new', BASE + '/<string:kind>/<int:record_id>'], type='http', auth='user', website=True, methods=['GET'])
    def detail(self, kind, record_id=None, company_id=None, **kw):
        if not request.env.user.share:
            return request.redirect('/odoo')
        service = self._service()
        company = service._company(company_id)
        try:
            if not record_id:
                service._actor('preparer', kind=kind)
            data = service._detail(company, kind, record_id)
        except AccessError:
            raise NotFound()
        return request.render(PREFIX + 'detail', self._values(service, company, kind=kind, title=KINDS[kind][1], boot_json=json.dumps(data).replace('<', '\\u003c')))

    @http.route(BASE + '/api/<string:operation>', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def api(self, operation, **post):
        service = self._service()
        try:
            if request.httprequest.content_length and request.httprequest.content_length > 2000000:
                raise ValidationError(_('Request is too large.'))
            data = json.loads(post.get('payload') or '{}')
            if not isinstance(data, dict):
                raise ValidationError(_('Invalid request.'))
            with request.env.cr.savepoint():
                company = service._company(data.get('company_id'))
                kind = data.get('kind', 'bills')
                service._kind(kind)
                if operation == 'options':
                    result = service._options(company, data.get('resource'), data.get('q', ''), kind, data.get('partner_id'), data.get('offset', 0), data.get('limit', 30))
                elif operation in ('product-defaults', 'product-read', 'product-create', 'product-update'):
                    result = service._product_operation(company, kind, operation, data)
                elif operation == 'defaults':
                    result = service._defaults(company, kind, data.get('partner_id'))
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

    @http.route(BASE + '/<string:kind>/<int:record_id>/attachments', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def upload(self, kind, record_id, company_id=None, version=None, **post):
        service = self._service()
        company = service._company(company_id)
        try:
            service._actor('preparer', kind=kind)
            with request.env.cr.savepoint():
                record = service._record(company, kind, record_id)
                record._pbw_accounting_lock(version)
                if not service._detail(company, kind, record_id)['editable']:
                    raise AccessError(_('Attachments can only be added to an editable draft.'))
                upload = request.httprequest.files.get('file')
                if not upload or not upload.filename:
                    raise ValidationError(_('Choose a file.'))
                blob = upload.read(15000001)
                if len(blob) > 15000000:
                    raise ValidationError(_('Maximum attachment size is 15 MB.'))
                attachment = service._env(company)['ir.attachment'].create({'name': upload.filename.rsplit('/', 1)[-1][:200], 'type': 'binary', 'datas': base64.b64encode(blob), 'res_model': record._name, 'res_id': record.id, 'company_id': company.id, 'public': False})
                service._audit(record, 'Attached supporting document', attachment.name)
            return request.redirect(BASE + '/%s/%s?company_id=%s' % (kind, record_id, company.id))
        except (AccessError, UserError, ValidationError) as exc:
            return request.make_response(str(exc), status=400)

    @http.route(BASE + '/<string:kind>/<int:record_id>/attachment/<int:attachment_id>', type='http', auth='user', website=True, methods=['GET'])
    def download(self, kind, record_id, attachment_id, company_id=None, **kw):
        service = self._service()
        company = service._company(company_id)
        record = service._record(company, kind, record_id)
        attachment = service._env(company)['ir.attachment'].search([('id', '=', attachment_id), ('res_model', '=', record._name), ('res_id', '=', record.id), ('type', '=', 'binary')], limit=1)
        if not attachment:
            raise NotFound()
        return request.make_response(base64.b64decode(attachment.datas or b''), headers=[('Content-Type', 'application/octet-stream'), ('Content-Disposition', content_disposition(attachment.name)), ('X-Content-Type-Options', 'nosniff')])

    @http.route(BASE + '/<string:kind>/<int:record_id>/print', type='http', auth='user', website=True, methods=['GET'])
    def print_record(self, kind, record_id, company_id=None, journal_entry=None, **kw):
        service = self._service()
        company = service._company(company_id)
        record = service._record(company, kind, record_id)
        report_xmlid = 'portal_backend_workspace.accounting__report_journal' if journal_entry == '1' or kind == 'journals' else 'account.account_invoices'
        report_env = service._env(company)
        report = report_env.ref(report_xmlid).sudo()
        if report.model != 'account.move' or report.report_type != 'qweb-pdf':
            raise UserError(_('The configured report is not an accounting PDF.'))
        pdf, _format = report_env['ir.actions.report']._render_qweb_pdf(report.id, res_ids=[record.id])
        return request.make_response(pdf, headers=[('Cache-Control', 'private, no-store'), ('Content-Type', 'application/pdf'), ('Content-Disposition', content_disposition((record.name or 'Draft').replace('/', '-') + '.pdf')), ('X-Content-Type-Options', 'nosniff')])
