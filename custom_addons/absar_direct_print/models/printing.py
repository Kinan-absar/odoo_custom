import base64
import hashlib
import json
import secrets
from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

MAX_PDF = 25 * 1024 * 1024

class PrintStation(models.Model):
    _name = 'absar.print.station'
    _description = 'Office Print Station'
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    allowed_user_ids = fields.Many2many('res.users', string='Allowed users', help='Empty allows all Direct Print users in this company.')
    printer_name = fields.Char(string='Windows printer name', help='Leave empty to use the desktop default printer.')
    last_seen = fields.Datetime(readonly=True)
    client_printers = fields.Text(readonly=True)
    token_hash = fields.Char(copy=False, groups='absar_direct_print.group_print_manager')
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
    absar_print_enabled = fields.Boolean(string='Show print options', default=False)
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
    _description = 'Choose How to Print'
    name = fields.Char(readonly=True)
    report_id = fields.Many2one('ir.actions.report', required=True, readonly=True)
    payload = fields.Text(required=True, readonly=True)
    station_id = fields.Many2one('absar.print.station', default=lambda s:s.env.user.absar_print_station_id)
    copies = fields.Integer(default=1)
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
        return {'type':'ir.actions.act_window','res_model':self._name,'res_id':w.id,'view_mode':'form','views':[(False, 'form')],'target':'new'}
    def _report_args(self):
        self.ensure_one()
        self.check_access('read')
        if self.create_uid != self.env.user:
            raise AccessError(_('This print request belongs to another user.'))
        report = self.report_id
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
    def action_browser(self):
        self._report_args()
        return {'type':'ir.actions.act_url','url':'/absar-print/browser/%s' % self.id,'target':'new'}
    def action_download(self):
        self._report_args()
        return {'type':'ir.actions.act_url','url':'/absar-print/download/%s' % self.id,'target':'download'}
    def action_office(self):
        report, ids, data = self._report_args()
        if not self.station_id:
            raise UserError(_('Select an office print station.'))
        self.station_id._check_sender()
        if not 1 <= self.copies <= 20:
            raise UserError(_('Copies must be between 1 and 20.'))
        pdf = report._render_qweb_pdf(report.report_name, ids, data=data)[0]
        if len(pdf) > MAX_PDF:
            raise UserError(_('This PDF exceeds the 25 MB print limit.'))
        # Create as sudo only after report rendering under the requesting user's permissions.
        job = self.env['absar.print.job'].sudo().create({'name':self.name,'station_id':self.station_id.id,
            'user_id':self.env.uid, 'copies':self.copies,
            'printer_name':self.station_id.printer_name, 'pdf_data':base64.b64encode(pdf)})
        return {'type':'ir.actions.client','tag':'display_notification','params':{
            'title':_('Queued for office printing'), 'message':_('Job #%s will be received by %s when its app is online.') % (job.id,self.station_id.name),
            'type':'success','sticky':False,'next':{'type':'ir.actions.act_window_close'}}}
