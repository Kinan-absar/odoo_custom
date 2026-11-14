"""Administrator-triggered fixtures; installation alone creates no business records."""
import base64
import secrets
from datetime import timedelta

from odoo import fields, models, _
from odoo.exceptions import AccessError, UserError

from .scenarios import EMPLOYEE_CASES, MATERIAL_CASES, EMPLOYEE_STEPS, MATERIAL_STEPS, MATERIALS, line_state
from .sample_pdf import sample_pdf


class EmployeeRequest(models.Model):
    _inherit = 'employee.request'

    recording_demo_batch_id = fields.Many2one('employee.portal.recording.demo', readonly=True, copy=False, index=True, ondelete='restrict')
    recording_demo_scenario = fields.Char(string='Demo Scenario', readonly=True, copy=False)


class MaterialRequest(models.Model):
    _inherit = 'material.request'

    recording_demo_batch_id = fields.Many2one('employee.portal.recording.demo', readonly=True, copy=False, index=True, ondelete='restrict')
    recording_demo_scenario = fields.Char(string='Demo Scenario', readonly=True, copy=False)


class RecordingDemo(models.Model):
    _name = 'employee.portal.recording.demo'
    _description = 'Employee Portal Recording Demo Setup'
    _order = 'id desc'

    name = fields.Char(required=True, default='Odoo Beyond — Backend Recording')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    state = fields.Selection([('draft', 'Not Created'), ('ready', 'Ready')], default='draft', readonly=True)
    confirmed_demo = fields.Boolean(string='This is a development/demo database')
    code = fields.Char(readonly=True, copy=False)
    demo_password = fields.Char(string='Sample Portal Password', readonly=True, copy=False, groups='base.group_system')
    login_summary = fields.Text(readonly=True, groups='base.group_system')
    employee_request_ids = fields.One2many('employee.request', 'recording_demo_batch_id', readonly=True)
    material_request_ids = fields.One2many('material.request', 'recording_demo_batch_id', readonly=True)
    employee_count = fields.Integer(compute='_compute_counts')
    material_count = fields.Integer(compute='_compute_counts')
    include_draft_documents = fields.Boolean(string='Include draft RFQ and draft vendor bill', default=True)
    result_summary = fields.Text(readonly=True)
    generator_version = fields.Char(string='Generator Version', compute='_compute_counts')

    manager_user_id = fields.Many2one('res.users', string='Direct Manager', default=lambda self: self.env.user, domain="[('active', '=', True), ('company_ids', 'in', [company_id])]")
    hr_user_id = fields.Many2one('res.users', string='HR', default=lambda self: self.env.user, domain="[('active', '=', True), ('company_ids', 'in', [company_id])]")
    finance_user_id = fields.Many2one('res.users', string='Finance', default=lambda self: self.env.user, domain="[('active', '=', True), ('company_ids', 'in', [company_id])]")
    ceo_user_id = fields.Many2one('res.users', string='CEO', default=lambda self: self.env.user, domain="[('active', '=', True), ('company_ids', 'in', [company_id])]")
    purchase_user_id = fields.Many2one('res.users', string='Purchase Representative', default=lambda self: self.env.user, domain="[('active', '=', True), ('company_ids', 'in', [company_id])]")
    store_user_id = fields.Many2one('res.users', string='Store Manager', default=lambda self: self.env.user, domain="[('active', '=', True), ('company_ids', 'in', [company_id])]")
    project_manager_user_id = fields.Many2one('res.users', string='Project Manager', default=lambda self: self.env.user, domain="[('active', '=', True), ('company_ids', 'in', [company_id])]")
    director_user_id = fields.Many2one('res.users', string='Projects Director', default=lambda self: self.env.user, domain="[('active', '=', True), ('company_ids', 'in', [company_id])]")

    def _compute_counts(self):
        for rec in self:
            rec.generator_version = '18.0.1.20.139'
            rec.employee_count = len(rec.employee_request_ids)
            rec.material_count = len(rec.material_request_ids)

    def _check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only a Settings administrator can create recording samples.'))
        if self.company_id not in self.env.companies:
            raise AccessError(_('Enable the selected company in your current session.'))

    def _resolve_demo_approvers(self):
        """Repair old saved setups whose added approver fields are empty/inactive.

        This writes only the setup record, never res.users or security groups.
        Existing eligible choices remain unchanged. Current active company user is
        preferred; an existing company administrator is the secondary fallback.
        """
        self.ensure_one()
        self._check_admin()
        current = self.env.user.sudo()
        fallback = current if current.active and self.company_id in current.company_ids else False
        if not fallback:
            fallback = self.env['res.users'].sudo().search([
                ('active', '=', True), ('company_ids', 'in', self.company_id.ids),
                ('groups_id', 'in', self.env.ref('base.group_system').ids),
            ], order='id', limit=1)
        keys = ('manager', 'hr', 'finance', 'ceo', 'purchase', 'store', 'project_manager', 'director')
        users, updates = {}, {}
        for key in keys:
            field_name = key + '_user_id'
            selected = self[field_name].sudo()
            if selected and selected.active and self.company_id in selected.company_ids:
                users[key] = selected
                continue
            if not fallback:
                label = self._fields[field_name].string
                raise UserError(_('No active company administrator is available for %s. Select an existing active approver with access to the chosen company.') % label)
            users[key] = fallback
            updates[field_name] = fallback.id
        if updates:
            self.write(updates)
        return users

    def _workflow(self, env, project, applies_to, steps, users):
        workflow = env['employee.portal.workflow'].sudo().create({
            'name': '%s — %s' % (project.name, 'Employee Approvals' if applies_to == 'employee_request' else 'Material Approvals'),
            'company_id': self.company_id.id, 'project_id': project.id, 'applies_to': applies_to,
            'active': False,
            'step_ids': [(0, 0, {'name': label, 'sequence': (index + 1) * 10,
                                'approver_type': 'user', 'user_id': users[key].id, 'sla_hours': 24})
                         for index, (key, label) in enumerate(steps)],
        })
        workflow.action_validate_workflow()
        workflow.write({'active': True})
        return workflow

    def _snapshot(self, env, request, workflow, steps, users, case, now):
        if case['stage'] == 'draft':
            return
        values = []
        for index, step in enumerate(workflow.step_ids.sorted('sequence')):
            status = line_state(index, case)
            key = steps[index][0]
            user = users[key]
            pending = now - timedelta(days=8, hours=-index * 3)
            if status == 'pending' and not case.get('overdue'):
                pending = now - timedelta(hours=2)
            vals = {
                'employee_request_id' if request._name == 'employee.request' else 'material_request_id': request.id,
                'workflow_id': workflow.id, 'source_step_id': step.id, 'sequence': step.sequence,
                'name': step.name, 'approver_type': 'user', 'approver_user_ids': [(6, 0, user.ids)],
                'state': status,
            }
            if status != 'waiting':
                vals['pending_date'] = pending
                vals['due_date'] = pending + timedelta(hours=24)
            if status == 'approved':
                vals.update(approved_by=user.id, approved_date=pending + timedelta(hours=2),
                            comment='Sample approval: reviewed against the project requirement.')
            elif status == 'returned':
                vals.update(returned_by=user.id, returned_date=pending + timedelta(hours=2),
                            return_reason='Please clarify the requested amount/specification and attach supporting documents.',
                            return_count=1)
            elif status == 'rejected':
                vals.update(rejected_by=user.id, rejected_date=pending + timedelta(hours=2),
                            comment='Sample rejection: duplicate request or requirement not justified.')
            elif status == 'pending' and case.get('overdue'):
                vals['is_overdue'] = True
            if case.get('override') and index == len(steps) - 1:
                vals.update(approved_by=self.env.user.id, override_by=self.env.user.id,
                            override_date=pending + timedelta(hours=2),
                            override_reason='Demo: responsible approver unavailable; urgent requirement reviewed by administrator.')
            values.append(vals)
        env['employee.portal.workflow.approval.line'].sudo().create(values)

    def _attachment(self, env, request, filename, category, title, extra=None):
        lines = [title, 'Request: ' + request.name, 'Scenario: ' + request.recording_demo_scenario,
                 'Project: ' + request.project_id.name, 'For screen recording only; no payment is due.']
        lines += extra or []
        env['ir.attachment'].sudo().create({
            'name': filename, 'type': 'binary', 'datas': base64.b64encode(sample_pdf(lines)),
            'mimetype': 'application/pdf', 'res_model': request._name, 'res_id': request.id,
            'description': category,
        })

    def action_create_samples(self):
        self.ensure_one()
        self._check_admin()
        # Serialize double clicks and reject attempts to duplicate an existing batch.
        self.env.cr.execute('SELECT id FROM employee_portal_recording_demo WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if self.state == 'ready':
            return self._reopen()
        if not self.confirmed_demo:
            raise UserError(_('Confirm this is a demo database. The sample requests appear in normal operational reports.'))
        company_env = self.with_company(self.company_id).env
        env = company_env(context=dict(company_env.context, tracking_disable=True, mail_create_nosubscribe=True,
                                   mail_create_nolog=True, no_reset_password=True, mail_notrack=True))
        # Request status is set at creation to avoid transition notifications; no approval actions,
        # PDF finalization mails, Telegram calls, or real accounting postings are invoked.
        code = secrets.token_hex(6)
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)
        roles = [
            ('manager', 'Daniel Reed', 'group_employee_portal_manager'),
            ('hr', 'Sarah Collins', 'group_employee_portal_hr'),
            ('finance', 'Omar Hassan', 'group_employee_portal_finance'),
            ('ceo', 'Emma Carter', 'group_employee_portal_ceo'),
            ('purchase', 'Anita Patel', 'group_mr_purchase_rep'),
            ('store', 'Noah Wilson', 'group_mr_store_manager'),
            ('project_manager', 'James Taylor', 'group_mr_project_manager'),
            ('director', 'Sofia Martin', 'group_mr_projects_director'),
        ]
        users = self._resolve_demo_approvers()
        role_employees = {}
        for key, name, group in roles:
            # Backend recording fixtures never create, edit, or regroup login accounts.
            # Existing accounts can be selected as approvers in this setup.
            role_employees[key] = env['hr.employee'].sudo().create({
                'name': name + ' (Demo)', 'user_id': False, 'job_title': dict(EMPLOYEE_STEPS + MATERIAL_STEPS)[key],
                'company_id': self.company_id.id,
            })
        projects, locations, workflows = [], [], []
        for label in ['Riverside Fit-Out', 'Northgate Site Development']:
            project = env['project.project'].sudo().create({
                'name': 'Demo — %s [%s]' % (label, code), 'company_id': self.company_id.id,
                'store_manager_employee_id': role_employees['store'].id,
                'project_manager_employee_id': role_employees['project_manager'].id,
            })
            location = env['hr.work.location'].sudo().create({
                'name': 'Demo — ' + label, 'company_id': self.company_id.id,
                'address_id': self.company_id.partner_id.id,
            })
            env['hr.work.location.project'].sudo().create({
                'work_location_id': location.id, 'project_id': project.id, 'geo_enforce': False,
            })
            projects.append(project)
            locations.append(location)
            workflows.append({
                'employee.request': self._workflow(env, project, 'employee_request', EMPLOYEE_STEPS, users),
                'material.request': self._workflow(env, project, 'material_request', MATERIAL_STEPS, users),
            })
        employees = []
        for index, name in enumerate(['Alex Morgan', 'Maya Adams', 'Liam Parker', 'Zara Khan']):
            employees.append(env['hr.employee'].sudo().create({
                'name': name + ' (Demo)', 'user_id': False, 'company_id': self.company_id.id,
                'job_title': ['Site Engineer', 'Project Coordinator', 'Site Supervisor', 'Quantity Surveyor'][index],
                'parent_id': role_employees['manager'].id,
                'work_location_id': locations[index % 2].id,
                'work_location_ids': [(6, 0, [locations[index % 2].id])],
            }))
        for model, cases, steps in [('employee.request', EMPLOYEE_CASES, EMPLOYEE_STEPS),
                                    ('material.request', MATERIAL_CASES, MATERIAL_STEPS)]:
            for index, case in enumerate(cases):
                employee = employees[index % len(employees)]
                project_index = index % 2
                workflow = workflows[project_index][model]
                stage = case['stage']
                state = stage if stage in ('draft', 'approved') else case.get('outcome', 'workflow')
                vals = {'name': 'DEMO-%s-%s-%02d' % ('ER' if model == 'employee.request' else 'MR', code, index + 1),
                        'employee_id': employee.id, 'project_id': projects[project_index].id,
                        'request_date': today - timedelta(days=10 + index % 5),
                        'state': state, 'recording_demo_batch_id': self.id, 'recording_demo_scenario': case['label']}
                if stage != 'draft':
                    vals['workflow_id'] = workflow.id
                if case.get('outcome') == 'rejected':
                    vals.update(state_before_reject='workflow', rejected_by=users[steps[stage][0]].id)
                if model == 'employee.request':
                    vals.update(request_type=case['kind'], description=self._employee_description(case, index))
                    if case['kind'] in ('leave', 'vacation_settlement'):
                        vals.update(leave_from=today + timedelta(days=31), leave_to=today + timedelta(days=47))
                else:
                    items = MATERIALS[index % len(MATERIALS)]
                    vals.update(worksite=locations[project_index].name,
                                delivery_date=today + timedelta(days=7 + index % 5),
                                no_po_required=case.get('no_po', False),
                                accounting_docs_status=case.get('docs', 'pending'),
                                quotation_status_override=case.get('exception', False),
                                line_ids=[(0, 0, {'item_name': name, 'qty_required': qty,
                                                'uom_id': env.ref('uom.product_uom_unit').id}) for name, qty in items])
                request = env[model].sudo().create(vals)
                self._snapshot(env, request, workflow, steps, users, case, now)
                if model == 'employee.request':
                    self._attachment(env, request, 'Sample_Supporting_Document.pdf', 'General',
                                     'Supporting document for ' + case['label'])
                # An internal note avoids in-app recipient fan-out and carries the fictional scenario label.
                request.message_post(body=_('DEMO SAMPLE — %s. Historical statuses are seeded examples for recording, not real approvals.') % case['label'],
                                     message_type='comment', subtype_xmlid='mail.mt_note')
                if model == 'material.request':
                    self._material_documents(env, request, case, users, now, code, index)
        self.write({'state': 'ready', 'code': code, 'demo_password': False,
                    'login_summary': 'Backend recording mode: no login accounts were created or changed.',
                    'result_summary': 'Created %s employee requests and %s material requests, 2 projects and 4 requesting employees. Existing selected users are the workflow approvers; no login accounts were created or changed. '
                                      'Includes real sample PDFs, seeded approval history, corrections, clarification, overdue steps and accounting-document tracking. '
                                      'No journal entries, confirmed purchase orders or stock receipts were posted.' % (len(EMPLOYEE_CASES), len(MATERIAL_CASES))})
        return self._reopen()

    def _employee_description(self, case, index):
        descriptions = {
            'leave': 'I would like to request annual leave for the dates below. I will complete the handover and coordinate coverage with my manager.',
            'letter': 'Please issue an employment and salary certificate addressed To Whom It May Concern for my personal banking application.',
            'advance': 'I request a salary advance of 2,500 in company currency, to be recovered over five monthly installments of 500, subject to approval.',
            'housing': 'Please review my housing allowance request for the upcoming assignment and confirm the applicable entitlement.',
            'training': 'I request approval to attend a two-day project planning course. The estimated fee is 1,200 in company currency.',
            'travel': 'Please approve a three-day business trip to attend the project coordination and handover meeting.',
            'medical': 'Please review reimbursement of 350 in company currency for an eligible medical consultation. Sample receipt attached.',
            'bank': 'Please update my salary bank details after HR verifies the supporting bank confirmation. This sample contains no real bank account.',
            'asset': 'I request a laptop and site inspection tablet to support project reporting and material tracking.',
            'transfer': 'Please review my transfer to the project coordination team, subject to the receiving manager and HR approvals.',
            'vacation_settlement': 'Please review my vacation settlement calculation for the leave period indicated below.',
            'exit': 'Please begin the clearance review and confirm the equipment handover and outstanding obligations.',
        }
        return descriptions[case['kind']] + '\n\nDemo recording example — no real financial or employment action is requested.'

    def _material_documents(self, env, request, case, users, now, code, index):
        for number in range(case['quotes']):
            self._attachment(env, request, 'Sample_Quotation_%s.pdf' % (number + 1), 'Quotation Documents',
                             'Quotation from Demo Supplier %s' % (number + 1),
                             ['Reference: DEMO-Q-%s-%s' % (index + 1, number + 1),
                              'Sample total: %s in company currency' % (1800 + number * 175)])
        self._attachment(env, request, 'Sample_Site_Requirement.pdf', 'General', 'Site material requirement',
                         ['%s: %s units' % (line.item_name, line.qty_required) for line in request.line_ids])
        docs = case.get('docs', 'pending')
        if docs != 'pending' or case.get('uploaded'):
            self._attachment(env, request, 'Sample_Invoice.pdf', 'Accounting Documents', 'SAMPLE INVOICE',
                             ['Invoice reference: DEMO-INV-%s' % (index + 1), 'Sample total: 1,950 in company currency'])
            if docs != 'pending':
                request.write({'docs_submitted_by': users['purchase'].id,
                               'docs_submitted_date': now - timedelta(days=1),
                               'accounting_docs_submitted_attachment_count': 1,
                               'accounting_docs_note': {'need_more': 'Please attach the delivery note and a clearer invoice copy.',
                                                        'processed': 'Demo documents checked and processed; no accounting entry was posted.',
                                                        'rejected': 'Demo invoice rejected: supplier reference does not match.'}.get(docs, 'Sample invoice documents submitted for accounting review.')})
        if case.get('extra_doc'):
            self._attachment(env, request, 'Sample_Delivery_Note.pdf', 'Accounting Documents', 'SAMPLE DELIVERY NOTE')
        if case.get('clarification') or case.get('replied'):
            request._write_clarification({
                'needs_clarification': bool(case.get('clarification')),
                'clarification_stage': 'workflow' if case.get('clarification') else False,
                'clarification_question': 'Please confirm the pump capacity and required connection diameter.',
                'clarification_requested_by': users['project_manager'].id,
                'clarification_requested_on': now - timedelta(hours=4),
                'clarification_step_name': 'Project Manager',
                'clarification_reply': 'Required capacity is 5 m3/h with a 50 mm connection. The specification is confirmed.' if case.get('replied') else False,
                'clarification_replied_on': now - timedelta(hours=1) if case.get('replied') else False,
            })
        if self.include_draft_documents and (case.get('rfq') or case.get('bill')):
            supplier = env['res.partner'].sudo().create({'name': 'Demo Supplier — %s [%s]' % (index + 1, code),
                                                        'supplier_rank': 1, 'email': False, 'company_id': self.company_id.id})
            if case.get('rfq'):
                product = env['product.product'].sudo().create({
                    'name': 'Demo project supplies [%s]' % code, 'type': 'consu',
                    'purchase_ok': True, 'sale_ok': False, 'company_id': self.company_id.id,
                    'uom_id': env.ref('uom.product_uom_unit').id,
                    'uom_po_id': env.ref('uom.product_uom_unit').id,
                })
                env['purchase.order'].sudo().create({
                    'partner_id': supplier.id, 'company_id': self.company_id.id,
                    'currency_id': self.company_id.currency_id.id, 'material_request_id': request.id,
                    'origin': request.name,
                    'order_line': [(0, 0, {'name': line.item_name, 'product_id': product.id, 'product_qty': line.qty_required,
                                          'product_uom': line.uom_id.id, 'price_unit': 25,
                                          'date_planned': fields.Datetime.now() + timedelta(days=7)}) for line in request.line_ids],
                })
            if case.get('bill'):
                account = env['account.account'].sudo().search([
                    ('company_ids', 'in', [self.company_id.id]), ('account_type', 'in', ['expense', 'expense_direct_cost']),
                    ('deprecated', '=', False)], limit=1)
                journal = env['account.journal'].sudo().search([('company_id', '=', self.company_id.id), ('type', '=', 'purchase')], limit=1)
                if not account or not journal:
                    raise UserError(_('A purchase journal and expense account are needed for the optional draft vendor bill. Configure them, or untick Include draft RFQ and draft vendor bill and run again. No partial samples are retained.'))
                request.write({'expense_account_id': account.id})
                env['account.move'].sudo().create({
                    'move_type': 'in_invoice', 'partner_id': supplier.id, 'company_id': self.company_id.id,
                    'journal_id': journal.id, 'invoice_date': fields.Date.context_today(self),
                    'ref': 'DEMO-INVOICE-%s-%s' % (code, index + 1), 'material_request_id': request.id,
                    'invoice_line_ids': [(0, 0, {'name': line.item_name, 'quantity': line.qty_required,
                                                 'price_unit': 10, 'account_id': account.id,
                                                 'product_uom_id': line.uom_id.id, 'tax_ids': [(5, 0, 0)]}) for line in request.line_ids],
                })

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'current'}

    def action_view_employee(self):
        self.ensure_one()
        self._check_admin()
        action = self.env['ir.actions.actions']._for_xml_id('employee_portal_suite.action_employee_request')
        action.update(domain=[('recording_demo_batch_id', '=', self.id)], context={})
        return action

    def action_view_material(self):
        self.ensure_one()
        self._check_admin()
        action = self.env['ir.actions.actions']._for_xml_id('employee_portal_suite.action_material_request')
        action.update(domain=[('recording_demo_batch_id', '=', self.id)], context={})
        return action
