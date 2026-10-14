import base64
import io

from lxml import etree
from psycopg2 import sql
try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.absar_sign_workflow_core.tools.signature_anchors import resolve_signature_placements

# These adapters have important specialized behavior (attachments, voucher locks,
# and revision rules) and deliberately continue to own their existing buttons.
SPECIALIZED_MODELS = {'purchase.order', 'account.payment.voucher',
                      'construction.contract', 'construction.measurement', 'construction.ipc'}


def button_arch(action_id, has_header):
    root = etree.Element('data')
    if has_header:
        target = etree.SubElement(root, 'xpath', expr='/form/header', position='inside')
    else:
        target = etree.SubElement(root, 'xpath', expr='/form/*[1]', position='before')
        target = etree.SubElement(target, 'header')
    etree.SubElement(target, 'button', name=str(action_id), type='action',
                     string='Send to Sign', icon='fa-pencil',
                     groups='sign.group_sign_user')
    return etree.tostring(root, encoding='unicode')


class UniversalIntegration(models.Model):
    _name = 'absar.sign.universal.integration'
    _description = 'Universal Signing Integration'
    _order = 'name, id'

    name = fields.Char(required=True)
    active = fields.Boolean(default=False)
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', readonly=True)
    report_id = fields.Many2one('ir.actions.report', required=True, ondelete='restrict',
                               domain="[('model', '=', model_name), ('report_type', '=', 'qweb-pdf')]")
    form_view_ids = fields.Many2many('ir.ui.view', string='Form Views',
                                    domain="[('model', '=', model_name), ('type', '=', 'form'), ('mode', '=', 'primary')]")
    project_field_id = fields.Many2one('ir.model.fields', string='Project Field',
                                      domain="[('model_id', '=', model_id), ('ttype', '=', 'many2one'), ('relation', '=', 'project.project')]")
    state_field_id = fields.Many2one('ir.model.fields', string='State Field',
                                    domain="[('model_id', '=', model_id), ('ttype', 'in', ['selection', 'char'])]")
    allowed_states = fields.Char(help='Technical values separated by commas, e.g. sale,done or posted. Leave both state settings empty to allow any state.')
    auto_send = fields.Boolean(string='Send Directly When Placement Is Ready', default=False,
                              help='Otherwise open the prepared template for review and use its native Send button.')
    action_id = fields.Many2one('ir.actions.server', readonly=True, copy=False, ondelete='set null')
    generated_view_ids = fields.One2many('ir.ui.view', 'absar_universal_integration_id', readonly=True, copy=False)

    _sql_constraints = [('unique_model', 'unique(model_id)', 'Only one universal integration is allowed per model.')]

    @api.onchange('model_id')
    def _onchange_model(self):
        self.report_id = False
        self.form_view_ids = False
        self.project_field_id = False
        self.state_field_id = False
        self.allowed_states = False

    def _validate_configuration(self):
        self.ensure_one()
        name = self.model_id.model
        if name not in self.env:
            raise ValidationError(_('The selected model is not available.'))
        Model = self.env[name]
        if Model._abstract or Model._transient or not Model._auto or name.startswith(('ir.', 'sign.', 'absar.sign.', 'res.users')):
            raise ValidationError(_('Choose a persistent business document model.'))
        company_field = Model._fields.get('company_id')
        if company_field and (company_field.type != 'many2one' or company_field.comodel_name != 'res.company'):
            raise ValidationError(_('The company field must refer to a company.'))
        if name in SPECIALIZED_MODELS or 'action_send_to_sign' in dir(type(Model)):
            raise ValidationError(_('This model already has a specialized Send to Sign integration. Keep using its existing button.'))
        if self.report_id.model != name or self.report_id.report_type != 'qweb-pdf':
            raise ValidationError(_('Choose a PDF report belonging to the selected model.'))
        if any(view.model != name or view.type != 'form' or view.mode != 'primary' for view in self.form_view_ids):
            raise ValidationError(_('Choose primary form views belonging to the selected model.'))
        for field in (self.project_field_id, self.state_field_id):
            if field and field.model_id != self.model_id:
                raise ValidationError(_('Field mappings must belong to the selected model.'))
        if self.project_field_id and (self.project_field_id.ttype != 'many2one' or self.project_field_id.relation != 'project.project'):
            raise ValidationError(_('The project field must refer to a project.'))
        if self.state_field_id and self.state_field_id.ttype not in ('selection', 'char'):
            raise ValidationError(_('The state field must be a selection or text field.'))
        if bool(self.state_field_id) != bool((self.allowed_states or '').strip()):
            raise ValidationError(_('Set both a State Field and Allowed States, or leave both empty.'))
        if self.state_field_id and not self._allowed_state_values():
            raise ValidationError(_('Enter at least one allowed state value.'))

    def _allowed_state_values(self):
        return [value.strip() for value in (self.allowed_states or '').split(',') if value.strip()]

    def _register_generated_record(self, record, label):
        self.env['ir.model.data'].sudo().create({
            'module': 'absar_send_to_sign_universal',
            'name': '%s_%s_%s' % (label, self.id, record.id),
            'model': record._name, 'res_id': record.id, 'noupdate': True,
        })

    def _sync_buttons(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only an administrator can configure signing buttons.'))
        for integration in self:
            integration.generated_view_ids.sudo().unlink()
            if not integration.active:
                if integration.action_id:
                    integration.action_id.sudo().write({'binding_model_id': False})
                continue
            integration._validate_configuration()
            views = integration.form_view_ids or self.env['ir.ui.view'].sudo().search([
                ('model', '=', integration.model_id.model), ('type', '=', 'form'),
                ('mode', '=', 'primary'), ('active', '=', True),
            ])
            if not views:
                raise UserError(_('No primary form views exist for this model.'))
            values = {
                'name': _('Send to Sign'), 'model_id': integration.model_id.id,
                'state': 'code', 'binding_model_id': integration.model_id.id,
                'binding_view_types': 'form',
                'code': "action = env['absar.sign.universal.integration'].browse(%s).action_send(records)" % integration.id,
            }
            if integration.action_id:
                integration.action_id.sudo().write(values)
            else:
                action = self.env['ir.actions.server'].sudo().create(values)
                # Store metadata without triggering a recursive synchronization.
                super(UniversalIntegration, integration).write({'action_id': action.id})
                integration._register_generated_record(action, 'action')
            for view in views:
                combined = view._get_combined_arch()
                if isinstance(combined, str):
                    combined = etree.fromstring(combined.encode())
                if combined.xpath("//button[@type='action' and @name='%s']" % integration.action_id.id):
                    continue
                generated = self.env['ir.ui.view'].sudo().create({
                    'name': 'absar.universal.sign.%s.%s' % (integration.id, view.id),
                    'model': integration.model_id.model, 'type': 'form',
                    'inherit_id': view.id, 'mode': 'extension', 'priority': 99,
                    'arch_db': button_arch(integration.action_id.id, bool(combined.xpath('/form/header'))),
                    'absar_universal_integration_id': integration.id,
                })
                integration._register_generated_record(generated, 'view')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._validate_configuration()
        records._sync_buttons()
        return records

    def write(self, vals):
        if {'action_id', 'generated_view_ids'}.intersection(vals):
            raise AccessError(_('Generated button metadata cannot be edited directly.'))
        if 'model_id' in vals and self.env['absar.sign.universal.document'].sudo().search_count([('integration_id', 'in', self.ids)]):
            raise UserError(_('A model with signing history cannot be changed. Create a separate integration.'))
        result = super().write(vals)
        for rec in self:
            rec._validate_configuration()
        self._sync_buttons()
        return result

    def unlink(self):
        self.generated_view_ids.sudo().unlink()
        actions = self.mapped('action_id')
        result = super().unlink()
        actions.sudo().unlink()
        return result

    def action_refresh_buttons(self):
        self._sync_buttons()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @api.model
    def _relocate_menu(self):
        parent = self.env.ref('absar_sign_workflow_core.menu_absar_signing_workflows').parent_id
        self.env.ref('absar_send_to_sign_universal.menu_universal_signing').sudo().write({'parent_id': parent.id})
        history = self.env.ref('absar_send_to_sign_universal.menu_universal_history', raise_if_not_found=False)
        if history:
            history.sudo().write({'parent_id': parent.parent_id.id or parent.id})

    def _check_source(self, record):
        self.ensure_one()
        if not self.env.user.has_group('sign.group_sign_user'):
            raise AccessError(_('You need Odoo Sign user access.'))
        if not self.active:
            raise UserError(_('This universal signing integration is inactive.'))
        if not record or len(record) != 1 or record._name != self.model_id.model:
            raise UserError(_('Select exactly one saved document of the configured model.'))
        record.check_access_rights('read')
        record.check_access_rule('read')
        record.check_access_rights('write')
        record.check_access_rule('write')
        company = record.company_id if 'company_id' in record._fields and record.company_id else self.env.company
        if company.id not in self.env.companies.ids:
            raise AccessError(_('The document belongs to a company outside your allowed companies.'))
        if self.state_field_id and record[self.state_field_id.name] not in self._allowed_state_values():
            raise UserError(_('This document cannot be sent in its current state. Allowed states: %s') % self.allowed_states)
        if self.report_id.groups_id and not (self.report_id.groups_id & self.env.user.groups_id):
            raise AccessError(_('You do not have access to the configured PDF report.'))
        return company

    def _get_workflow(self, record, company):
        name = self.project_field_id.name if self.project_field_id else 'project_id'
        field = record._fields.get(name)
        project = record[name] if field and field.type == 'many2one' and field.comodel_name == 'project.project' else False
        Workflow = self.env['absar.sign.workflow']
        domain = [('active', '=', True), ('is_template', '=', False),
                  ('model_id', '=', self.model_id.id), ('company_id', '=', company.id)]
        workflow = Workflow.search(domain + [('project_id', '=', project.id)], limit=1) if project else False
        workflow = workflow or Workflow.search(domain + [('project_id', '=', False)], limit=1)
        if not workflow:
            raise UserError(_('Configure an active Signing Workflow for this model and company first.'))
        workflow._validate_configuration()
        if any(not step.signer_user_id.active for step in workflow.step_ids):
            raise UserError(_('All signer users must be active.'))
        roles = workflow.step_ids.mapped('sign_role_id')
        if len(roles) != len(workflow.step_ids.filtered('sign_role_id')):
            raise UserError(_('Each workflow step must use a different Odoo Sign role.'))
        # Resolve names too, detecting duplicate role names before creating a PDF.
        role_ids = [step._ensure_sign_role().id for step in workflow.step_ids]
        if len(set(role_ids)) != len(role_ids):
            raise UserError(_('Each workflow step must use a different Odoo Sign role.'))
        return workflow

    def action_send(self, records=None, new_revision=False):
        self.ensure_one()
        if records is None:
            if self.env.context.get('active_model') != self.model_id.model:
                raise UserError(_('Open the document before sending it to Sign.'))
            ids = self.env.context.get('active_ids') or [self.env.context.get('active_id')]
            records = self.env[self.model_id.model].browse([value for value in ids if value]).exists()
        self._validate_configuration()
        company = self._check_source(records)
        # Lock the source row, never changing its business fields. This serializes
        # preparation across users/tabs and prevents duplicate native requests.
        self.env.cr.execute(sql.SQL('SELECT id FROM {} WHERE id = %s FOR UPDATE').format(sql.Identifier(records._table)), [records.id])
        records.invalidate_recordset()
        company = self._check_source(records)
        Document = self.env['absar.sign.universal.document']
        existing = Document.sudo().search([
            ('integration_id', '=', self.id), ('source_id', '=', records.id),
        ], order='id desc', limit=1)
        if existing:
            existing = existing.with_user(self.env.user)
            existing._source()
            if not new_revision:
                return existing.action_open_signing()
            existing.invalidate_recordset(['request_id', 'state'])
            if existing.request_id and existing.request_id.state not in ('signed', 'canceled', 'refused', 'expired'):
                raise UserError(_('An existing signature request is still active. Finish or cancel it in Odoo Sign before preparing a new revision.'))
            existing.template_id.check_access_rights('write')
            existing.template_id.check_access_rule('write')
        workflow = self._get_workflow(records, company)
        pdf, _format = self.env['ir.actions.report']._render_qweb_pdf(self.report_id.id, records.ids)
        pages = len(PdfReader(io.BytesIO(pdf)).pages)
        if not pages:
            raise UserError(_('The configured report produced an empty PDF.'))
        positions, issues = resolve_signature_placements(pdf, pages, workflow.step_ids, prefer_signature_area=True)
        revision = Document.sudo().search_count([('integration_id', '=', self.id), ('source_id', '=', records.id)]) + 1
        name = '%s - %s - R%s.pdf' % (self.name, records.display_name, revision)
        attachment = self.env['ir.attachment'].create({
            'name': name, 'datas': base64.b64encode(pdf), 'type': 'binary',
            'mimetype': 'application/pdf', 'res_model': records._name, 'res_id': records.id,
        })
        # Keep universal source linkage separate from bridge callbacks: arbitrary
        # business models must never be written by a Sign status callback.
        template = self.env['sign.template'].create({
            'name': name[:-4], 'attachment_id': attachment.id, 'absar_workflow_id': workflow.id,
        })
        self.env['absar.sign.workflow.service'].with_context(
            absar_sign_anchors=positions, absar_sign_bottom=True, absar_sign_page=pages,
        )._prepare_template_signature_items(template, workflow)
        snapshot = [{'user_id': step.signer_user_id.id, 'partner_id': step.signer_partner_id.id,
                     'role_id': step._ensure_sign_role().id, 'order': order}
                    for order, step in enumerate(workflow.step_ids.sorted('sequence'), 1)]
        document = Document.sudo().create({
            'integration_id': self.id, 'source_model': records._name, 'source_id': records.id,
            'name': records.display_name, 'company_id': company.id, 'user_id': self.env.user.id,
            'template_id': template.id, 'workflow_id': workflow.id,
            'placement_issues': '\n'.join(issues), 'signer_snapshot': snapshot, 'revision': revision,
        }).with_user(self.env.user)
        template.write({'absar_universal_document_id': document.id})
        if self.auto_send and not issues:
            return document.action_send_ready()
        action = document.action_open_signing()
        if issues:
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'title': _('Placement review required · Not sent'), 'message': ' '.join(issues),
                'type': 'warning', 'sticky': True, 'next': action,
            }}
        return action


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'
    absar_universal_integration_id = fields.Many2one('absar.sign.universal.integration', ondelete='cascade', copy=False)
