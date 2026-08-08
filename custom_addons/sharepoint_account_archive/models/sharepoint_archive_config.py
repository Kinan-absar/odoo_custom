import json
import logging
import re
from urllib.parse import quote

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GRAPH_ROOT = 'https://graph.microsoft.com/v1.0'
TOKEN_URL = 'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
MAX_SIMPLE_UPLOAD = 250 * 1024 * 1024


class SharePointArchiveConfig(models.Model):
    _name = 'sharepoint.archive.config'
    _description = 'SharePoint Accounting Archive Configuration'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        ondelete='cascade', index=True,
    )
    active = fields.Boolean(default=True)
    tenant_id = fields.Char(required=True)
    client_id = fields.Char(required=True)
    client_secret = fields.Char(required=True, groups='base.group_system')
    hostname = fields.Char(
        required=True,
        help='Example: contoso.sharepoint.com',
    )
    site_path = fields.Char(
        required=True,
        default='/sites/Finance',
        help='Example: /sites/Finance',
    )
    drive_name = fields.Char(
        required=True,
        default='Documents',
        help='SharePoint document library name, usually Documents or Shared Documents.',
    )
    root_folder = fields.Char(
        default='Accounting Archive', required=True,
        help='Root folder created/used inside the selected document library.',
    )
    site_id = fields.Char(readonly=True)
    drive_id = fields.Char(readonly=True)
    auto_archive = fields.Boolean(default=True)
    archive_entries = fields.Boolean(string='Journal Entries / JVs', default=True)
    archive_vendor_bills = fields.Boolean(default=True)
    archive_customer_invoices = fields.Boolean(default=True)
    include_attachments = fields.Boolean(default=True)
    last_test_at = fields.Datetime(readonly=True)
    last_test_message = fields.Char(readonly=True)

    _sql_constraints = [
        ('company_unique', 'unique(company_id)', 'Only one SharePoint archive configuration is allowed per company.'),
    ]

    @api.model
    def _get_for_company(self, company):
        return self.search([('company_id', '=', company.id), ('active', '=', True)], limit=1)

    def _token(self):
        self.ensure_one()
        try:
            response = requests.post(
                TOKEN_URL.format(tenant_id=self.tenant_id.strip()),
                data={
                    'client_id': self.client_id.strip(),
                    'client_secret': self.client_secret,
                    'scope': 'https://graph.microsoft.com/.default',
                    'grant_type': 'client_credentials',
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            raise UserError(_('Could not contact Microsoft identity platform: %s') % exc) from exc
        if not response.ok:
            raise UserError(_('Microsoft authentication failed (%s): %s') % (response.status_code, response.text[:1000]))
        return response.json()['access_token']

    def _headers(self, content_type=None):
        headers = {'Authorization': 'Bearer %s' % self._token()}
        if content_type:
            headers['Content-Type'] = content_type
        return headers

    def _graph(self, method, path, **kwargs):
        self.ensure_one()
        url = path if path.startswith('http') else GRAPH_ROOT + path
        kwargs.setdefault('timeout', 60)
        try:
            response = requests.request(method, url, headers=self._headers(kwargs.pop('content_type', None)), **kwargs)
        except requests.RequestException as exc:
            raise UserError(_('Microsoft Graph request failed: %s') % exc) from exc
        if not response.ok:
            raise UserError(_('Microsoft Graph error %s on %s: %s') % (response.status_code, path, response.text[:1500]))
        if response.status_code == 204 or not response.content:
            return {}
        content_type = response.headers.get('Content-Type', '')
        return response.json() if 'json' in content_type else response.content

    def action_test_connection(self):
        for rec in self:
            rec._resolve_site_and_drive()
            rec.write({
                'last_test_at': fields.Datetime.now(),
                'last_test_message': _('Connection successful. Site and document library resolved.'),
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('SharePoint'),
                'message': _('Connection successful.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def _resolve_site_and_drive(self):
        self.ensure_one()
        site_path = '/' + self.site_path.strip('/')
        site = self._graph('GET', '/sites/%s:%s' % (self.hostname.strip(), site_path))
        site_id = site.get('id')
        if not site_id:
            raise UserError(_('Microsoft Graph did not return a SharePoint site ID.'))
        drives = self._graph('GET', '/sites/%s/drives' % quote(site_id, safe='')).get('value', [])
        wanted = self.drive_name.strip().lower()
        drive = next((item for item in drives if (item.get('name') or '').strip().lower() == wanted), None)
        if not drive:
            names = ', '.join(sorted(item.get('name', '') for item in drives)) or _('none')
            raise UserError(_('Document library "%s" was not found. Available libraries: %s') % (self.drive_name, names))
        self.write({'site_id': site_id, 'drive_id': drive['id']})
        return site_id, drive['id']

    def _ensure_ready(self):
        self.ensure_one()
        if not self.site_id or not self.drive_id:
            self._resolve_site_and_drive()
        return self.drive_id

    @api.model
    def _safe_name(self, value):
        value = (value or '').strip()
        value = re.sub(r'[~#%&*{}\\:<>?/+|"\']', '-', value)
        value = re.sub(r'\s+', ' ', value).strip(' .')
        return value[:180] or 'Unnamed'

    def _get_item_by_path(self, path):
        self.ensure_one()
        drive_id = quote(self._ensure_ready(), safe='')
        encoded = '/'.join(quote(part, safe='') for part in path.strip('/').split('/') if part)
        try:
            return self._graph('GET', '/drives/%s/root:/%s' % (drive_id, encoded))
        except UserError as exc:
            if 'error 404' in str(exc).lower():
                return False
            raise

    def _ensure_folder_path(self, path):
        self.ensure_one()
        drive_id = quote(self._ensure_ready(), safe='')
        current = self._graph('GET', '/drives/%s/root' % drive_id)
        current_path = []
        for raw_part in [p for p in path.strip('/').split('/') if p]:
            part = self._safe_name(raw_part)
            current_path.append(part)
            existing = self._get_item_by_path('/'.join(current_path))
            if existing:
                current = existing
                continue
            payload = {'name': part, 'folder': {}, '@microsoft.graph.conflictBehavior': 'fail'}
            try:
                current = self._graph(
                    'POST',
                    '/drives/%s/items/%s/children' % (drive_id, quote(current['id'], safe='')),
                    json=payload,
                    content_type='application/json',
                )
            except UserError:
                # Another worker may have created the folder between GET and POST.
                current = self._get_item_by_path('/'.join(current_path))
                if not current:
                    raise
        return current

    def _delete_item_by_path(self, path):
        self.ensure_one()
        item = self._get_item_by_path(path)
        if not item:
            return False
        drive_id = quote(self._ensure_ready(), safe='')
        item_id = quote(item['id'], safe='')
        self._graph('DELETE', '/drives/%s/items/%s' % (drive_id, item_id))
        return True

    def _upload_bytes(self, parent_item_id, filename, content, mimetype='application/octet-stream'):
        self.ensure_one()
        if len(content) > MAX_SIMPLE_UPLOAD:
            raise UserError(_('Attachment %s is larger than 250 MB. Large upload sessions are not enabled in this version.') % filename)
        drive_id = quote(self._ensure_ready(), safe='')
        safe_filename = self._safe_name(filename)
        path = '/drives/%s/items/%s:/%s:/content' % (
            drive_id,
            quote(parent_item_id, safe=''),
            quote(safe_filename, safe=''),
        )
        return self._graph('PUT', path, data=content, content_type=mimetype or 'application/octet-stream')

    def _document_type_folder(self, move):
        if move.move_type in ('in_invoice', 'in_refund'):
            return 'Vendor Bills'
        if move.move_type in ('out_invoice', 'out_refund'):
            return 'Customer Invoices'
        return 'Journal Vouchers'

    def _move_is_enabled(self, move):
        self.ensure_one()
        if move.move_type in ('in_invoice', 'in_refund'):
            return self.archive_vendor_bills
        if move.move_type in ('out_invoice', 'out_refund'):
            return self.archive_customer_invoices
        return self.archive_entries
