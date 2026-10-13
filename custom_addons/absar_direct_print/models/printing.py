import base64
import hashlib
import json
import secrets
from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

MAX_PDF = 25 * 1024 * 1024


def _account_move_report_kind(report):
    """Return the supported account.move print purpose for an Odoo report."""
    report_name = (getattr(report, 'report_name', '') or '').lower()
    label = (getattr(report, 'name', '') or '').lower().strip()
    if 'journal' in report_name or 'voucher' in report_name or 'journal' in label or 'voucher' in label:
        return 'journal'
    # Only the unified invoice PDF belongs in this chooser. Older Studio copies,
    # tax-invoice buttons and unrelated reports should not be selectable here.
    if report_name == 'absar_report_suite.invoice' or label == 'invoice':
        return 'invoice'
    return False


def _filter_account_move_reports(reports, move_types=None):
    """Keep only a move's valid reports and put its Journal Voucher first."""
    categories = {'journal'}
    if not move_types or set(move_types).issubset({
            'in_invoice', 'in_refund', 'out_invoice', 'out_refund', 'in_receipt', 'out_receipt'}):
        categories.add('invoice')
    eligible = [report for report in reports if _account_move_report_kind(report) in categories]
    eligible.sort(key=lambda report: (
        0 if _account_move_report_kind(report) == 'journal' else 1,
        (getattr(report, 'name', '') or '').casefold(),
        getattr(report, 'id', 0),
    ))
    return eligible

class PrintStation(models.Model):
    _name = 'absar.print.station'
    _description = 'Office Print Station'
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    allowed_user_ids = fields.Many2many('res.users', string='Allowed users', help='Empty allows all Direct Print users in this company.')
    printer_name = fields.Char(string='Default Windows printer', help='Optional default for this computer. Choose another detected printer in the print dialog.')
    printer_ids = fields.One2many('absar.print.printer', 'station_id', string='Detected printers', readonly=True)
    last_seen = fields.Datetime(readonly=True)
    client_printers = fields.Text(readonly=True)
    token_hash = fields.Char(copy=False, groups='absar_direct_print.group_print_manager')
    def _sync_printers(self, names):
        """Update the read-only printer directory from this station's authenticated app."""
        self.ensure_one()
        if not isinstance(names, list):
            return
        clean = list(dict.fromkeys(name for name in names[:100]
                                   if isinstance(name, str) and name.strip() and len(name) <= 500))
        directory = self.env['absar.print.printer'].sudo().with_context(active_test=False)
        existing = directory.search([('station_id', '=', self.id)])
        by_name = {printer.name: printer for printer in existing}
        for name in clean:
            if name in by_name:
                if not by_name[name].active:
                    by_name[name].write({'active': True})
            else:
                directory.create({'name': name, 'station_id': self.id})
        existing.filtered(lambda printer: printer.active and printer.name not in clean).write({'active': False})
        self.sudo().write({'client_printers': json.dumps(clean, ensure_ascii=False)})

    def action_pair(self):
        self.ensure_one()
        if not self.env.user.has_group('absar_direct_print.group_print_manager'):
            raise AccessError(_('Only print managers can pair a station.'))
        token = secrets.token_urlsafe(48)
        self.token_hash = hashlib.sha256(token.encode()).hexdigest()
        pair = self.env['absar.print.pair'].create({'station_id': self.id, 'token': token})
        return {'type':'ir.actions.act_window', 'res_model':pair._name, 'res_id':pair.id,
                'view_mode':'form', 'views':[(False, 'form')], 'target':'new'}
    def action_revoke(self):
        if not self.env.user.has_group('absar_direct_print.group_print_manager'):
            raise AccessError(_('Only print managers can revoke a station.'))
        self.write({'token_hash': False})
    def _check_sender(self):
        self.ensure_one()
        if not self.active or self.company_id not in self.env.companies:
            raise AccessError(_('This station is unavailable for your company.'))
        if self.allowed_user_ids and self.env.user not in self.allowed_user_ids:
            raise AccessError(_('You are not allowed to use this station.'))

class PrintPrinter(models.Model):
    _name = 'absar.print.printer'
    _description = 'Detected Windows Printer'
    _order = 'name, id'
    name = fields.Char(required=True, readonly=True)
    station_id = fields.Many2one('absar.print.station', required=True, readonly=True, ondelete='cascade')
    company_id = fields.Many2one(related='station_id.company_id', store=True, readonly=True)
    active = fields.Boolean(default=True, readonly=True)
    _sql_constraints = [('station_printer_unique', 'unique(station_id, name)',
                         'A printer can only be listed once per station.')]

class PrintPair(models.TransientModel):
    _name = 'absar.print.pair'
    _description = 'Print Station Pairing'
    station_id = fields.Many2one('absar.print.station', readonly=True)
    token = fields.Char(readonly=True)
    url = fields.Char(compute='_compute_url')
    @api.depends('station_id')
    def _compute_url(self):
        for r in self:
            r.url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

class PrintUser(models.Model):
    _inherit = 'res.users'
    absar_print_enabled = fields.Boolean(string='Show Print button', default=False)
    absar_print_station_id = fields.Many2one('absar.print.station', string='Default office station')
    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['absar_print_enabled', 'absar_print_station_id']
    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['absar_print_enabled', 'absar_print_station_id']
    @api.model
    def absar_print_preferences(self):
        return {'enabled': self.env.user.absar_print_enabled and self.env.user.has_group('absar_direct_print.group_print_user')}

class PrintJob(models.Model):
    _name = 'absar.print.job'
    _description = 'Office Print Job'
    _order = 'id desc'
    name = fields.Char(required=True, readonly=True)
    station_id = fields.Many2one('absar.print.station', required=True, readonly=True, ondelete='restrict')
    company_id = fields.Many2one(related='station_id.company_id', store=True)
    user_id = fields.Many2one('res.users', required=True, default=lambda s:s.env.user, readonly=True)
    state = fields.Selection([('queued','Queued'), ('claimed','Processing'), ('submitted','Sent to Windows'), ('failed','Failed'), ('uncertain','Needs review'), ('cancelled','Cancelled')], default='queued', readonly=True)
    copies = fields.Integer(default=1, readonly=True)
    printer_name = fields.Char(readonly=True)
    pdf_data = fields.Binary(readonly=True, attachment=False, groups='absar_direct_print.group_print_manager')
    claimed_at = fields.Datetime(readonly=True)
    claim_id = fields.Char(readonly=True, groups='absar_direct_print.group_print_manager')
    finished_at = fields.Datetime(readonly=True)
    message = fields.Text(readonly=True)
    @api.constrains('copies')
    def _check_copies(self):
        if any(not 1 <= r.copies <= 20 for r in self):
            raise ValidationError(_('Copies must be between 1 and 20.'))
    def action_cancel(self):
        self.check_access('read')
        for r in self:
            if r.state != 'queued':
                raise UserError(_('Only queued jobs can be cancelled.'))
            # Avoid cancellation racing with the agent claim.
            self.env.cr.execute('SELECT id FROM absar_print_job WHERE id=%s FOR UPDATE', [r.id])
            r.invalidate_recordset(['state'])
            if r.state != 'queued':
                raise UserError(_('The station has already picked up this job.'))
            r.sudo().write({'state':'cancelled', 'pdf_data':False})
    def action_retry(self):
        if not self.env.user.has_group('absar_direct_print.group_print_manager'):
            raise AccessError(_('Only a print manager can retry a job.'))
        for r in self:
            self.env.cr.execute('SELECT id FROM absar_print_job WHERE id=%s FOR UPDATE', [r.id])
            r.invalidate_recordset(['state', 'pdf_data'])
            if r.state not in ('failed','uncertain'):
                raise UserError(_('Only failed or uncertain jobs can be retried.'))
            if not r.pdf_data:
                raise UserError(_('The document has expired. Generate a new print job.'))
            r.write({'state':'queued', 'claim_id':False, 'claimed_at':False, 'message':False})
    @api.model
    def _gc_jobs(self):
        self.sudo().search([('create_date','<',fields.Datetime.now()-timedelta(days=7)), ('pdf_data','!=',False)]).write({'pdf_data':False})
        self.sudo().search([('create_date','<',fields.Datetime.now()-timedelta(days=30))]).unlink()

class PrintWizard(models.TransientModel):
    _name = 'absar.print.wizard'
    _description = 'Print'
    name = fields.Char(readonly=True)
    report_id = fields.Many2one('ir.actions.report', required=True)
    payload = fields.Text(required=True, readonly=True)
    station_id = fields.Many2one('absar.print.station', default=lambda s:s.env.user.absar_print_station_id)
    printer_id = fields.Many2one('absar.print.printer', string='Printer',
        compute='_compute_printer_id', store=True, readonly=False, precompute=True,
        help='Choose a printer on this computer. Leave empty to use the station or Windows default.')
    copies = fields.Integer(default=1)

    @api.depends('station_id')
    def _compute_printer_id(self):
        for wizard in self:
            printers = wizard.station_id.printer_ids.filtered('active')
            preferred = printers.filtered(lambda printer: printer.name == wizard.station_id.printer_name)
            wizard.printer_id = preferred[:1] or (printers if len(printers) == 1 else False)

    def _print_destination(self):
        self.ensure_one()
        if not self.station_id:
            raise UserError(_('Select an office print station.'))
        self.station_id._check_sender()
        if self.printer_id:
            self.printer_id.check_access('read')
            if self.printer_id.station_id != self.station_id or not self.printer_id.active:
                raise UserError(_('This printer is unavailable for the selected station. Choose another printer.'))
            return self.printer_id.name
        return self.station_id.printer_name or ''

    @api.model
    def available_reports(self, model_name, view_type, record_ids=None):
        if not self.env.user.has_group('absar_direct_print.group_print_user'):
            return []
        if model_name not in self.env or view_type not in ('form', 'list'):
            return []
        self.env[model_name].check_access_rights('read')
        domain = [('model', '=', model_name), ('report_type', '=', 'qweb-pdf')]
        if model_name == 'account.move':
            # Invoice printing stays available in this chooser for invoices and
            # bills, while the native Print menu is reserved for Journal Voucher.
            domain += ['|', ('binding_model_id.model', '=', model_name),
                       ('report_name', 'in', ['absar_report_suite.invoice',
                                              'absar_report_suite.journal'])]
        else:
            domain += [('binding_model_id.model', '=', model_name), ('binding_type', '=', 'report')]
        reports = self.env['ir.actions.report'].search(domain)
        reports = reports.filtered(lambda r:
            (model_name == 'account.move' and _account_move_report_kind(r))
            or (model_name != 'account.move' and r.binding_type == 'report'
                and view_type in (r.binding_view_types or '').split(',')))
        reports = reports.filtered(lambda r: not r.groups_id or r.groups_id & self.env.user.groups_id)
        if model_name == 'account.move':
            params = self.env['ir.config_parameter'].sudo()
            route_ids = set()
            for alias in ('journal_report', 'invoice_report'):
                value = params.get_param('absar_report_suite.target.' + alias)
                if value and value.isdigit():
                    route_ids.add(int(value))
            if route_ids:
                reports = reports.filtered(lambda r: r.id in route_ids)
            moves = self.env[model_name].browse(record_ids or []).exists()
            move_types = set(moves.mapped('move_type')) if moves else None
            reports = _filter_account_move_reports(reports, move_types)
        return [{'id': r.id, 'name': r.name} for r in reports]

    @api.model
    def open_for_records(self, model_name, ids, view_type):
        if not isinstance(ids, list) or not ids or any(type(i) is not int or i <= 0 for i in ids):
            raise UserError(_('Select saved records to print.'))
        reports = self.available_reports(model_name, view_type, ids)
        if not reports:
            raise UserError(_('No PDF reports are available for this page.'))
        records = self.env[model_name].browse(ids).exists()
        records.check_access('read')
        if len(records) != len(set(ids)):
            raise UserError(_('Some selected records no longer exist.'))
        payload = {'context': {'active_model': model_name, 'active_ids': records.ids,
                              'active_id': records.ids[0]}, 'view_type': view_type, 'data': {}}
        wizard = self.create({'name': reports[0]['name'], 'report_id': reports[0]['id'],
                              'payload': json.dumps(payload)})
        return {'name': _('Print'), 'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': wizard.id, 'views': [(False, 'form')], 'view_mode': 'form', 'target': 'new'}

    available_report_ids = fields.Many2many('ir.actions.report', compute='_compute_available_reports')

    @api.depends('payload')
    def _compute_available_reports(self):
        for wizard in self:
            payload = json.loads(wizard.payload or '{}')
            model_name = (payload.get('context') or {}).get('active_model')
            if payload.get('view_type'):
                active_ids = (payload.get('context') or {}).get('active_ids')
                wizard.available_report_ids = [r['id'] for r in self.available_reports(
                    model_name, payload['view_type'], active_ids)]
            else:
                wizard.available_report_ids = wizard.report_id

    @api.model
    def open_report(self, action):
        if not self.env.user.has_group('absar_direct_print.group_print_user'):
            raise AccessError(_('Direct Print access is required.'))
        if not isinstance(action, dict) or action.get('report_type') != 'qweb-pdf':
            raise UserError(_('Only PDF reports are supported.'))
        report = self.env['ir.actions.report'].search([('report_name','=',action.get('report_name')), ('report_type','=','qweb-pdf')], limit=1)
        if not report:
            raise UserError(_('Report not found.'))
        if report.groups_id and not (report.groups_id & self.env.user.groups_id):
            raise AccessError(_('You cannot print this report.'))
        # Keep the original JSON-safe action/data for report wizards as well as record reports.
        safe = {'context': action.get('context') or {}, 'data': action.get('data') or {}}
        if len(json.dumps(safe)) > 1024*1024:
            raise UserError(_('Report options are too large.'))
        w = self.create({'name':report.name,'report_id':report.id,'payload':json.dumps(safe)})
        w._report_args()  # validate model access before opening preview or queueing
        return {'name':_('Print'),'type':'ir.actions.act_window','res_model':self._name,'res_id':w.id,'view_mode':'form','views':[(False, 'form')],'target':'new'}
    def _report_args(self):
        self.ensure_one()
        self.check_access('read')
        if self.create_uid != self.env.user:
            raise AccessError(_('This print request belongs to another user.'))
        report = self.report_id
        if report.report_type != 'qweb-pdf':
            raise UserError(_('Only PDF reports are supported.'))
        if report not in self.available_report_ids:
            raise AccessError(_('This report is unavailable for the selected records.'))
        if report.groups_id and not (report.groups_id & self.env.user.groups_id):
            raise AccessError(_('You cannot print this report.'))
        model = self.env[report.model]
        model.check_access_rights('read')
        payload = json.loads(self.payload)
        ctx = dict(self.env.context)
        original = payload.get('context') or {}
        # Do not accept privilege-changing context flags from a browser action.
        for key in ('lang','tz','active_model','active_id','active_ids'):
            if key in original:
                ctx[key] = original[key]
        ids = original.get('active_ids') or ([original['active_id']] if original.get('active_id') else [])
        if not isinstance(ids,list) or any(type(i) is not int or i <= 0 for i in ids):
            raise UserError(_('Invalid report records.'))
        if ids and original.get('active_model',report.model) != report.model:
            # Report actions generated by a wizard often use data rather than docids.
            if not payload.get('data'):
                raise UserError(_('The report model does not match the selected records.'))
            ids=[]
        model.browse(ids).check_access('read')
        return report.with_context(ctx), ids, payload.get('data') or None
    def action_office(self):
        report, ids, data = self._report_args()
        printer_name = self._print_destination()
        if not 1 <= self.copies <= 20:
            raise UserError(_('Copies must be between 1 and 20.'))
        pdf = report._render_qweb_pdf(report.report_name, ids, data=data)[0]
        if len(pdf) > MAX_PDF:
            raise UserError(_('This PDF exceeds the 25 MB print limit.'))
        # Create as sudo only after report rendering under the requesting user's permissions.
        job = self.env['absar.print.job'].sudo().create({'name':report.name,'station_id':self.station_id.id,
            'user_id':self.env.uid, 'copies':self.copies,
            'printer_name':printer_name, 'pdf_data':base64.b64encode(pdf)})
        return {'type':'ir.actions.client','tag':'display_notification','params':{
            'title':_('Queued for office printing'), 'message':_('Job #%s will be received by %s when its app is online.') % (job.id,self.station_id.name),
            'type':'success','sticky':False,'next':{'type':'ir.actions.act_window_close'}}}
