"""Opt-in recording fixtures. Installation never creates sample transactions."""
import base64
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


SCENARIOS = [
    ('draft', 'Draft - ready for employee submission', 'draft', True),
    ('mixed', 'Draft - mixed VAT and no-VAT expenses', 'draft', True),
    ('accounting', 'Awaiting accounting review', 'submitted', True),
    ('supervisor', 'Awaiting supervisor review', 'review_2', True),
    ('manager', 'Awaiting final approval', 'manager_approval', True),
    ('returned', 'Returned - missing fuel receipt', 'draft', True),
    ('revised', 'Returned - correct category and reference', 'draft', True),
    ('rejected', 'Rejected - personal expense', 'refused', False),
    ('approved_vat', 'Approved - VAT report ready for accounting', 'approved', True),
    ('approved', 'Approved - ready to create voucher', 'approved', False),
    ('draft_move', 'Approved - linked draft journal entry', 'approved', False),
    ('posted_move', 'Approved - linked posted journal entry', 'approved', False),
]


def sample_receipt_pdf(title, rows):
    """Dependency-free, one-page fictional receipt for attachment demonstrations."""
    def escaped(value):
        return str(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    text = ['DEMO RECEIPT - NOT A VALID TAX INVOICE', title] + list(rows) + [
        'Fictional Odoo Beyond recording sample. No goods or services supplied.']
    commands = ['BT /F1 14 Tf 45 780 Td']
    for index, line in enumerate(text):
        if index:
            commands.append('0 -30 Td')
        commands.append('(%s) Tj' % escaped(line))
    commands.append('ET')
    stream = '\n'.join(commands).encode('ascii', 'replace')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream']
    result = bytearray(b'%PDF-1.4\n');offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result));result.extend(('%d 0 obj\n' % number).encode() + obj + b'\nendobj\n')
    xref = len(result);result.extend(('xref\n0 %d\n0000000000 65535 f \n' % len(offsets)).encode())
    for offset in offsets[1:]:
        result.extend(('%010d 00000 n \n' % offset).encode())
    result.extend(('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(offsets), xref)).encode())
    return bytes(result)


class PettyCashRecordingDemo(models.Model):
    _name = 'petty.cash.recording.demo'
    _description = 'Petty Cash Recording Demo Setup'

    name = fields.Char(required=True, default='Odoo Beyond - Petty Cash Recording')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    backend_user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user,
        domain="[('active', '=', True), ('share', '=', False), ('company_ids', 'in', company_id)]",
        string='Backend Recording User')
    reviewer_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, string='Accounting Reviewer')
    supervisor_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, string='Accounting Supervisor')
    approver_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, string='Final Approver')
    prepare_roles = fields.Boolean(default=True, string='Enable petty cash roles for selected recording accounts',
        help='Adds petty cash preparer/configuration and selected review roles only. Never changes Portal/Internal user type. Existing accounting mappings are preserved.')
    include_posted = fields.Boolean(default=True, string='Include posted accounting examples')
    confirmed_demo = fields.Boolean(string='This is a development/demo database')
    state = fields.Selection([('draft', 'Not Created'), ('ready', 'Ready')], default='draft', readonly=True)
    created_by = fields.Many2one('res.users', readonly=True)
    created_on = fields.Datetime(readonly=True)
    summary = fields.Text(readonly=True)
    records_json = fields.Json(readonly=True, copy=False)

    _sql_constraints = [('one_demo_per_company', 'unique(company_id)',
        'A recording setup already exists for this company. Open that setup instead.')]

    def _demo_owners(self):
        self.ensure_one()
        return [('Backend', self.backend_user_id)]

    def _demo_validate(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(_('Only an Accounting Administrator can create recording examples.'))
        self.check_access_rights('write');self.check_access_rule('write')
        if self.company_id not in self.env.companies:
            raise AccessError(_('Select this company in the active companies first.'))
        if not self.confirmed_demo:
            raise UserError(_('Confirm this is a development/demo database. Sample reports and journal entries appear in ordinary lists and reports.'))
        if not self.backend_user_id or self.backend_user_id.share:
            raise UserError(_('Choose an existing internal user for backend recording.'))
        users = self.backend_user_id | self.reviewer_id | self.supervisor_id | self.approver_id
        for user in users:
            if not user.active or user._is_public() or self.company_id not in user.company_ids:
                raise UserError(_('Every selected recording/review account must be active and have access to this company.'))
        # Let an accounting/demo administrator repeat the build without duplicating data.
        return True

    def _demo_prepare_roles(self):
        if self.prepare_roles:
            role_map = [(self.backend_user_id, 'group_petty_cash_user'),
                        (self.backend_user_id, 'group_petty_cash_accountant'),
                        (self.reviewer_id, 'group_petty_cash_reviewer_1'),
                        (self.supervisor_id, 'group_petty_cash_reviewer_2'),
                        (self.approver_id, 'group_petty_cash_manager')]
            for user, role in role_map:
                group = self.env.ref('petty_cash_management.' + role)
                if group not in user.groups_id:
                    user.write({'groups_id': [(4, group.id)]})

    def _demo_configure_owner(self, user, accounts, journal, make):
        config = self.env['petty.cash.user.config'].search([
            ('partner_id', '=', user.partner_id.id), ('company_id', '=', self.company_id.id)], limit=1)
        if not config:
            make('petty.cash.user.config', {'partner_id': user.partner_id.id,
                'company_id': self.company_id.id, 'petty_cash_account_id': accounts['cash'].id,
                'input_vat_account_id': accounts['vat'].id, 'petty_cash_journal_id': journal.id})

    def action_create_examples(self):
        self.ensure_one();self._demo_validate()
        self.env.cr.execute('SELECT id FROM petty_cash_recording_demo WHERE id = %s FOR UPDATE', (self.id,))
        self.invalidate_recordset(['state'])
        if self.state == 'ready':
            return self.action_open_reports()
        actor = self.env.user
        with self.env.cr.savepoint():
            demo = self.sudo().with_company(self.company_id).with_context(
                tracking_disable=True, mail_create_nosubscribe=True, mail_create_nolog=True, mail_notrack=True)
            demo._demo_prepare_roles()
            demo._demo_build()
            demo.write({'state': 'ready', 'created_by': actor.id, 'created_on': fields.Datetime.now()})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form'}

    def action_open_reports(self):
        self.ensure_one();self._demo_validate()
        return {'type': 'ir.actions.act_window', 'name': _('Petty Cash Recording Examples'),
            'res_model': 'petty.cash', 'view_mode': 'list,form',
            'views': [(self.env.ref('petty_cash_management.view_petty_cash_recording_list').id, 'list'),
                      (self.env.ref('petty_cash_management.view_petty_cash_form').id, 'form')],
            'domain': [('recording_demo_id', '=', self.id)]}

    def action_open_entries(self):
        self.ensure_one();self._demo_validate()
        return {'type': 'ir.actions.act_window', 'name': _('Sample Accounting Entries'),
            'res_model': 'account.move', 'view_mode': 'list,form',
            'domain': [('id', 'in', (self.records_json or {}).get('account.move', []))]}

    def _demo_build(self):
        from .petty_cash import PettyCash
        from .review_workflow import _TOKEN
        company = self.company_id;today = fields.Date.context_today(self);registry = {}
        def make(model, values):
            rec = self.env[model].create(values);registry.setdefault(model, []).extend(rec.ids);return rec
        accounts = {}
        for number, key, name, kind in [
            (1,'cash','Petty Cash','asset_cash'), (2,'vat','Demo Input VAT','asset_current'),
            (3,'materials','Site Consumables','expense'),(4,'fuel','Fuel and Transport','expense'),
            (5,'office','Office and Printing','expense'),(6,'repairs','Repairs and Tools','expense'),
            (7,'welfare','Staff Welfare','expense'),(8,'other','Other Site Costs','expense')]:
            code = 'PCD%s%02d' % (self.id, number)
            while self.env['account.account'].search_count([('company_ids','in',company.ids),('code','=',code)]):code += 'X'
            accounts[key] = make('account.account', {'name': 'DEMO - '+name, 'code':code,
                'account_type':kind,'company_ids':[(6,0,company.ids)]})
        counter = self.id % 10000;code = 'D%04d' % counter
        while self.env['account.journal'].search_count([('company_id','=',company.id),('code','=',code)]):
            counter = (counter+1) % 10000;code = 'D%04d' % counter
        journal = make('account.journal', {'name':'Odoo Beyond Demo - Petty Cash','code':code,
            'type':'general','company_id':company.id,'default_account_id':accounts['other'].id})
        country = company.account_fiscal_country_id or company.country_id
        group_vals = {'name':'DEMO - Petty Cash VAT 15%','company_id':company.id}
        if country:group_vals['country_id'] = country.id
        tax_group = make('account.tax.group',group_vals)
        tax = make('account.tax', {'name':'DEMO - Input VAT 15%','amount':15,'amount_type':'percent',
            'type_tax_use':'purchase','company_id':company.id,'tax_group_id':tax_group.id,
            'invoice_repartition_line_ids':[(0,0,{'factor_percent':100,'repartition_type':'base'}),
                (0,0,{'factor_percent':100,'repartition_type':'tax','account_id':accounts['vat'].id})],
            'refund_repartition_line_ids':[(0,0,{'factor_percent':100,'repartition_type':'base'}),
                (0,0,{'factor_percent':100,'repartition_type':'tax','account_id':accounts['vat'].id})]})
        plan_values = {'name':'DEMO - Petty Cash Projects'}
        if 'company_id' in self.env['account.analytic.plan']._fields:plan_values['company_id'] = company.id
        analytic_plan = make('account.analytic.plan',plan_values)
        analytics = [make('account.analytic.account',{'name':'DEMO - '+name,'plan_id':analytic_plan.id,'company_id':company.id})
            for name in ['Riverside Site','Citygate Fit-Out']]
        categories = {}
        for index,(key,label) in enumerate([('materials','Site Consumables'),('fuel','Fuel and Transport'),
                ('office','Office and Printing'),('repairs','Repairs and Tools'),('welfare','Staff Welfare'),('other','Other Site Costs')]):
            categories[key] = make('petty.cash.category',{'name':'DEMO - '+label,'account_id':accounts[key].id,
                'tax_id':tax.id,'analytic_account_id':analytics[index % 2].id,'sequence':90+index})
        owners = self._demo_owners()
        for owner_index,(channel,user) in enumerate(owners):
            self._demo_configure_owner(user,accounts,journal,make)
            for index,(key,label,state,vat) in enumerate(SCENARIOS):
                report = make('petty.cash',{'user_id':user.id,'company_id':company.id,
                    'currency_id':company.currency_id.id,'date':today,
                    'petty_cash_account_id':accounts['cash'].id,'input_vat_account_id':accounts['vat'].id,
                    'journal_id':journal.id,'recording_demo_id':self.id,
                    'recording_demo_label':'%s - %s' % (channel,label)})
                # A visible prefix keeps sample accounting references unmistakable.
                report.write({'name':'DEMO / '+report.name})
                values = [('materials','Site Supply Centre','Fasteners and site consumables',180+index*12),
                          ('fuel','City Fuel Station','Site vehicle fuel',95+index*5),
                          ('office' if index%2==0 else 'repairs','Citygate Trading',
                           'Printing and stationery' if index%2==0 else 'Small tool repair',65+index*4)]
                if key=='rejected':
                    values=[('other','Personal Store','Personal headphones',240),
                            ('welfare','Corner Cafe','Personal weekend meal',85),
                            ('other','Apparel Outlet','Personal clothing',120)]
                for number,(cat,supplier,description,amount) in enumerate(values,1):
                    line = make('petty.cash.line',{'petty_cash_id':report.id,
                        'date':today-timedelta(days=(index+number)%6),'supplier':'DEMO - '+supplier,
                        'invoice_number':'DEMO-R-%s-%s-%s' % (owner_index+1,index+1,number),
                        'po_number':'DEMO-PO-%03d' % (100+index) if number==1 and key!='rejected' else False,
                        'mr_number':'DEMO-MR-%03d' % (200+index) if number!=2 and key!='rejected' else False,
                        'zone':('Not project related' if key=='rejected' else 'Riverside - Zone A' if index%2==0 else 'Citygate - Level 2'),
                        'description':'DEMO - '+description,'category_id':categories[cat].id,
                        'amount_before_vat':amount,'vat_applicable':vat and number!=2})
                    # Returned missing-receipt example intentionally lacks its fuel receipt.
                    if not (number==2 and key=='returned'):
                        pdf = sample_receipt_pdf(line.invoice_number,[
                            'Supplier: '+line.supplier,'Expense: '+description,'Date: '+str(line.date),
                            'Before VAT: %.2f %s' % (line.amount_before_vat, company.currency_id.name),
                            'VAT: %.2f' % line.vat_amount,'Total: %.2f' % line.amount_total])
                        att = make('ir.attachment',{'name':line.invoice_number+'.pdf','type':'binary',
                            'mimetype':'application/pdf','datas':base64.b64encode(pdf),
                            'res_model':'petty.cash','res_id':report.id})
                        line.write({'attachment_ids':[(4,att.id)]});report.write({'attachment_ids':[(4,att.id)]})
                history = {}
                if state in ('review_2','manager_approval','approved'):
                    history.update({'review_1_by':self.reviewer_id.id,'review_1_date':fields.Datetime.now()})
                if state in ('manager_approval','approved'):
                    history.update({'review_2_by':self.supervisor_id.id,'review_2_date':fields.Datetime.now()})
                if state=='approved':
                    history.update({'manager_approved_by':self.approver_id.id,'manager_approved_date':fields.Datetime.now()})
                if key in ('returned','revised','rejected'):
                    reason = {'returned':'Attach the missing fuel receipt, then resubmit.',
                        'revised':'Correct the expense category and add the material request reference.',
                        'rejected':'Personal expense is not eligible for company reimbursement.'}[key]
                    if key=='revised':history.update({'review_1_by':self.reviewer_id.id,'review_1_date':fields.Datetime.now()})
                    history.update({'correction_reason':reason,'returned_by':(self.supervisor_id if key=='revised' else self.reviewer_id).id,
                                    'returned_date':fields.Datetime.now()})
                report._flow_write(dict(history,state=state))
                report.message_post(body=_('Fictional recording example: %s. Review history is seeded for demonstration, not a real approval.') % label)
                if key in ('draft_move','posted_move'):
                    # Reuse normal accounting/tax/attachment generation. This private
                    # fixture builder is reachable only after administrator opt-in.
                    PettyCash.action_create_journal_entry(report.with_context(_petty_review_token=_TOKEN))
                    move = report.journal_entry_id
                    if not move or move.state!='draft':raise UserError(_('The sample draft voucher was not created.'))
                    registry.setdefault('account.move',[]).append(move.id)
                    if key=='posted_move' and self.include_posted:move.action_post()
        self.write({'records_json':registry,'summary':
            'Reports: %s\nExpense lines: %s\nReceipt attachments: %s\nAccounting entries: %s\n'
            'Expense categories: 6\nAnalytic projects: 2\nSubmitters: %s\n'
            'Includes VAT/no-VAT, mixed expenses, PO/MR references, missing receipt, returned, rejected, all review stages and accounting handoff.\n'
            'All transactions and review histories are fictional.' % (
                len(registry.get('petty.cash',[])),len(registry.get('petty.cash.line',[])),
                len(registry.get('ir.attachment',[])),len(registry.get('account.move',[])),
                ', '.join('%s: %s' % (label,user.name) for label,user in owners))})


class PettyCashRecordingExample(models.Model):
    _inherit = 'petty.cash'
    recording_demo_id = fields.Many2one('petty.cash.recording.demo',readonly=True,copy=False,ondelete='set null')
    recording_demo_label = fields.Char(string='Recording Example',readonly=True,copy=False)
