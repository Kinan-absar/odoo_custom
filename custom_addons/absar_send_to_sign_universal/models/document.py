from psycopg2 import sql

from odoo import api, Command, fields, models, _
from odoo.exceptions import AccessError, UserError


class UniversalDocument(models.Model):
    _name = 'absar.sign.universal.document'
    _description = 'Universal Document Signing History'
    _order = 'id desc'

    revision = fields.Integer(required=True, readonly=True, default=1)
    name = fields.Char(required=True, readonly=True)
    integration_id = fields.Many2one('absar.sign.universal.integration', required=True, ondelete='restrict', readonly=True)
    source_model = fields.Char(required=True, readonly=True)
    source_id = fields.Integer(required=True, readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True)
    user_id = fields.Many2one('res.users', required=True, readonly=True)
    template_id = fields.Many2one('sign.template', required=True, ondelete='restrict', readonly=True)
    workflow_id = fields.Many2one('absar.sign.workflow', ondelete='restrict', readonly=True)
    signer_snapshot = fields.Json(readonly=True)
    placement_issues = fields.Text(readonly=True)
    request_id = fields.Many2one('sign.request', compute='_compute_request')
    state = fields.Selection([
        ('prepared', 'Prepared · Not Sent'), ('sent', 'Signing in Progress'),
        ('signed', 'Fully Signed'), ('canceled', 'Cancelled'), ('refused', 'Refused'),
        ('expired', 'Expired'), ('other', 'Check Request'),
    ], compute='_compute_request')

    @api.depends('template_id')
    def _compute_request(self):
        for document in self:
            request = self.env['sign.request'].search([('template_id', '=', document.template_id.id)], order='id desc', limit=1)
            document.request_id = request
            document.state = request.state if request and request.state in ('sent', 'signed', 'canceled', 'refused', 'expired') else ('other' if request else 'prepared')

    def _source(self):
        self.ensure_one()
        self.check_access_rights('read')
        self.check_access_rule('read')
        if self.source_model not in self.env:
            raise UserError(_('The original model is no longer available.'))
        record = self.env[self.source_model].browse(self.source_id).exists()
        if not record:
            raise UserError(_('The original document no longer exists.'))
        record.check_access_rights('read')
        record.check_access_rule('read')
        return record

    def action_open_source(self):
        record = self._source()
        return {'type': 'ir.actions.act_window', 'name': record.display_name,
                'res_model': record._name, 'res_id': record.id, 'view_mode': 'form', 'target': 'current'}

    def action_open_signing(self):
        self._source()
        self.template_id.check_access_rights('read')
        self.template_id.check_access_rule('read')
        # Nonstored request state must be refreshed after native sending.
        self.invalidate_recordset(['request_id', 'state'])
        if self.request_id:
            return {'type': 'ir.actions.act_window', 'name': _('Signature Request'),
                    'res_model': 'sign.request', 'res_id': self.request_id.id,
                    'view_mode': 'form', 'target': 'current'}
        return {'type': 'ir.actions.act_url',
                'url': '/odoo/sign/%s/action-sign.Template?id=%s' % (self.template_id.id, self.template_id.id),
                'target': 'self'}

    def action_new_revision(self):
        record = self._source()
        return self.integration_id.action_send(record, new_revision=True)

    def action_send_ready(self):
        record = self._source()
        integration = self.integration_id
        integration._check_source(record)
        if self.placement_issues:
            raise UserError(_('Placement needs review. Open the template, adjust the fields and use its Send button.'))
        self.env.cr.execute(sql.SQL('SELECT id FROM {} WHERE id = %s FOR UPDATE').format(sql.Identifier(record._table)), [record.id])
        record.invalidate_recordset()
        integration._check_source(record)
        self.invalidate_recordset(['request_id', 'state'])
        if self.env['sign.request'].search_count([('template_id', '=', self.template_id.id)]):
            return self.action_open_signing()
        self._check_latest_preparation()
        template = self.template_id
        template.check_access_rights('write')
        template.check_access_rule('write')
        Wizard = self.env['sign.send.request'].with_context(
            active_model='sign.template', active_id=template.id, sign_template_id=template.id,
            default_template_id=template.id, default_has_default_template=True,
        )
        commands = Wizard._absar_signer_commands(template)
        self._validate_snapshot()
        values = {'template_id': template.id, 'subject': template.name,
                  'filename': template.attachment_id.name, 'signer_ids': commands}
        if 'has_default_template' in Wizard._fields:
            values['has_default_template'] = True
        if 'signers_count' in Wizard._fields:
            values['signers_count'] = len(self.signer_snapshot)
        if 'is_user_signer' in Wizard._fields:
            values['is_user_signer'] = False
        if 'signer_id' in Wizard._fields:
            values['signer_id'] = self.signer_snapshot[0]['partner_id'] if len(self.signer_snapshot) == 1 else False
        Wizard._absar_enable_signing_order_vals(values)
        wizard = Wizard.create(values)
        if 'has_default_template' in wizard._fields and not wizard.has_default_template:
            raise UserError(_('Odoo Sign did not initialize the template request. Nothing was sent.'))
        wizard.send_request()
        self.invalidate_recordset(['request_id', 'state'])
        if not self.request_id or self.request_id.state not in ('sent', 'signed'):
            raise UserError(_('Odoo Sign did not create a sent request.'))
        return self.action_open_signing()

    def _check_latest_preparation(self):
        self.ensure_one()
        latest = self.sudo().search([('integration_id', '=', self.integration_id.id), ('source_id', '=', self.source_id)], order='id desc', limit=1)
        if latest.id != self.id:
            raise UserError(_('This template was superseded by a newer signing revision. Open the latest preparation.'))

    def _validate_snapshot(self):
        self.ensure_one()
        if not self.signer_snapshot:
            raise UserError(_('No signer snapshot is available. Prepare a new template.'))
        for signer in self.signer_snapshot:
            user = self.env['res.users'].browse(signer['user_id']).exists()
            partner = self.env['res.partner'].browse(signer['partner_id']).exists()
            role = self.env['sign.item.role'].browse(signer['role_id']).exists()
            if not user or not user.active or not partner or not partner.email or not role or user.partner_id != partner:
                raise UserError(_('A prepared signer is unavailable or has no email. Prepare a new signing revision.'))


class SignTemplate(models.Model):
    _inherit = 'sign.template'
    absar_universal_document_id = fields.Many2one('absar.sign.universal.document', readonly=True, copy=False, ondelete='set null')


class SignSendRequest(models.TransientModel):
    _inherit = 'sign.send.request'

    @api.model
    def _absar_signer_commands(self, template):
        document = template.absar_universal_document_id if template else False
        if not document:
            return super()._absar_signer_commands(template)
        # Native template ACLs still govern access. The immutable snapshot is
        # necessary for users who can send a shared template but not its history.
        document = document.sudo()
        document._validate_snapshot()
        commands = [Command.clear()]
        Signer = self.env['sign.send.request.signer']
        for signer in document.signer_snapshot:
            values = {'partner_id': signer['partner_id'], 'role_id': signer['role_id']}
            if 'mail_sent_order' in Signer._fields:
                values['mail_sent_order'] = signer['order']
            commands.append(Command.create(values))
        return commands

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            template_id = values.get('template_id') or self.env.context.get('default_template_id')
            template = self.env['sign.template'].browse(template_id).exists() if template_id else False
            if template and template.absar_universal_document_id:
                if 'has_default_template' in self._fields:
                    values['has_default_template'] = True
                if 'signers_count' in self._fields:
                    values['signers_count'] = len(template.absar_universal_document_id.sudo().signer_snapshot)
        return super().create(vals_list)

    def create_request(self):
        self.ensure_one()
        document = self.template_id.absar_universal_document_id
        if document:
            # Metadata is read under sudo; source/report checks are performed
            # using the actual sender, including when Send is used in the editor.
            document = document.sudo()
            source = self.env[document.source_model].browse(document.source_id).exists()
            integration = document.integration_id.with_user(self.env.user)
            integration._check_source(source)
            self.env.cr.execute(sql.SQL('SELECT id FROM {} WHERE id = %s FOR UPDATE').format(sql.Identifier(source._table)), [source.id])
            source.invalidate_recordset()
            integration._check_source(source)
            document._validate_snapshot()
            document._check_latest_preparation()
            if self.env['sign.request'].sudo().search_count([('template_id', '=', self.template_id.id)]):
                raise UserError(_('This template already has a signature request. Open signing history instead of sending it again.'))
            actual = sorted((line.role_id.id, line.partner_id.id,
                             line.mail_sent_order if 'mail_sent_order' in line._fields else 0)
                            for line in self.signer_ids)
            expected = sorted((row['role_id'], row['partner_id'],
                               row['order'] if 'mail_sent_order' in self.env['sign.send.request.signer']._fields else 0)
                              for row in document.signer_snapshot)
            if actual != expected:
                raise UserError(_('Signers and signing order must match the prepared workflow. Prepare a new revision to use a different workflow.'))
            if 'has_default_template' in self._fields:
                self.has_default_template = True
            self._absar_enable_signing_order_record()
        return super().create_request()
