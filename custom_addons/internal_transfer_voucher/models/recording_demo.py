"""Explicit, opt-in recording fixtures. Never loaded by module installation."""
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class VoucherRecordingDemo(models.Model):
    _name = 'voucher.recording.demo'
    _description = 'Payment and Receipt Voucher Recording Setup'
    _check_company_auto = True

    name = fields.Char(default='Odoo Beyond — Voucher Recording', required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    confirmed_demo = fields.Boolean(string='This is a development/demo database')
    state = fields.Selection([('draft', 'Not Created'), ('ready', 'Ready')], default='draft', readonly=True)
    records_json = fields.Json(readonly=True, copy=False)
    summary = fields.Text(readonly=True)
    created_by = fields.Many2one('res.users', readonly=True)
    created_on = fields.Datetime(readonly=True)

    _sql_constraints = [('one_setup_per_company', 'unique(company_id)',
                         'A recording setup already exists for this company. Open that setup instead.')]

    def _check_demo_access(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(_('Only an Accounting Administrator can create recording examples.'))
        self.check_access_rights('write')
        self.check_access_rule('write')
        if self.company_id not in self.env.companies:
            raise AccessError(_('Select this company in your active companies first.'))

    def action_create_examples(self):
        self.ensure_one()
        self._check_demo_access()
        # Serialize double clicks. A failed fixture build rolls back as one unit.
        self.env.cr.execute('SELECT id FROM voucher_recording_demo WHERE id = %s FOR UPDATE', (self.id,))
        self.invalidate_recordset(['state'])
        if self.state == 'ready':
            return self._reload()
        if not self.confirmed_demo:
            raise UserError(_('Confirm this is a development/demo database. Examples include posted bills, invoices and vouchers and affect accounting reports.'))
        operator = self.env.user
        with self.env.cr.savepoint():
            # Sudo is scoped to new fixture records after explicit administrator and
            # company checks. No users, groups, real partners or settings are edited.
            setup = self.sudo().with_company(self.company_id).with_context(
                tracking_disable=True, mail_create_nosubscribe=True,
                mail_create_nolog=True, mail_notrack=True)
            setup._build_examples()
            setup.write({'state': 'ready', 'created_by': operator.id, 'created_on': fields.Datetime.now()})
        return self._reload()

    def _reload(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'current'}

    def action_open_examples(self):
        self.ensure_one()
        self._check_demo_access()
        model = self.env.context.get('demo_model')
        allowed = {'account.payment.voucher', 'account.receipt.voucher', 'cash.plan.run',
                   'cash.plan.line', 'cash.plan.review', 'purchase.order', 'account.move'}
        if model not in allowed:
            raise UserError(_('Choose an example list from the recording setup.'))
        return {'type': 'ir.actions.act_window', 'name': _('Recording Examples'),
                'res_model': model, 'view_mode': 'list,form',
                'domain': [('id', 'in', (self.records_json or {}).get(model, []))]}

    def _build_examples(self):
        self.ensure_one()
        company = self.company_id
        today = fields.Date.context_today(self)
        monday = today - timedelta(days=today.weekday())
        registry = {}

        def make(model, vals, **context):
            record = self.env[model].with_context(**context).create(vals)
            registry.setdefault(model, []).extend(record.ids)
            return record

        # Dedicated accounts/journals keep the fixture independent of a particular
        # chart of accounts, without changing journal or partner configuration.
        accounts = {}
        for number, key, label, kind, reconcile in [
            (1, 'bank', 'Demo Bank', 'asset_cash', False),
            (2, 'cash', 'Demo Cash', 'asset_cash', False),
            (3, 'payable', 'Demo Trade Payables', 'liability_payable', True),
            (4, 'receivable', 'Demo Trade Receivables', 'asset_receivable', True),
            (5, 'expense', 'Demo Site Expenses', 'expense', False),
            (6, 'income', 'Demo Project Revenue', 'income', False),
            (7, 'advance', 'Demo Supplier Advances', 'asset_prepayments', True),
            (8, 'loan', 'Demo Financing', 'liability_non_current', False),
        ]:
            code = 'OB%s%02d' % (self.id, number)
            while self.env['account.account'].search_count([('company_ids', 'in', company.id), ('code', '=', code)]):
                code += 'X'
            accounts[key] = make('account.account', {'name': 'Odoo Beyond — ' + label,
                'code': code, 'account_type': kind, 'reconcile': reconcile,
                'company_ids': [(6, 0, company.ids)]})

        journals = {}
        for index, key, kind, account in [(1, 'bank', 'bank', 'bank'), (2, 'cash', 'cash', 'cash'),
                                            (3, 'purchase', 'purchase', 'expense'), (4, 'sale', 'sale', 'income')]:
            code = 'O%03d%s' % (self.id % 1000, index)
            # account.journal codes are at most five characters.
            while self.env['account.journal'].search_count([('company_id', '=', company.id), ('code', '=', code)]):
                index += 4
                code = 'O%04d' % index
            journals[key] = make('account.journal', {'name': 'Odoo Beyond Demo — ' + key.title(),
                'code': code, 'type': kind, 'company_id': company.id,
                'default_account_id': accounts[account].id})

        partners = {}
        for key, label in [
            ('new', 'Atlas Building Supplies'), ('update', 'Cedar Electrical Supply'),
            ('keep', 'Summit Site Services'), ('obsolete', 'Clearwater Supplies'),
            ('po', 'Horizon Equipment'), ('convert', 'Meridian Steel'),
            ('draft', 'Pioneer Safety Supplies'), ('duplicate', 'Northstar Logistics'),
            ('customer', 'Riverside Development'), ('customer2', 'Citygate Projects'),
            ('workflow', 'Westbridge Operations'), ('staff', 'Site Payroll Team'), ('landlord', 'Office Leasing'), ('bank', 'Financing Partner')]:
            partners[key] = make('res.partner', {'name': 'DEMO — ' + label,
                'company_type': 'company', 'company_id': company.id,
                'supplier_rank': int(not key.startswith('customer')),
                'customer_rank': int(key.startswith('customer')),
                'property_account_payable_id': accounts['payable'].id,
                'property_account_receivable_id': accounts['receivable'].id})
        projects = [make('project.project', {'name': 'DEMO — ' + label, 'company_id': company.id})
                    for label in ['Riverside Site Expansion', 'Citygate Fit-Out']]
        product = make('product.product', {'name': 'DEMO — Site Procurement Package',
            'type': 'consu', 'purchase_method': 'receive', 'purchase_ok': True,
            'sale_ok': False, 'company_id': company.id,
            'property_account_expense_id': accounts['expense'].id,
            'taxes_id': [(5, 0, 0)], 'supplier_taxes_id': [(5, 0, 0)]})

        runs = []
        for offset, balance, budget, state in [(-7, 150000, 70000, 'done'),
                                               (0, 180000, 100000, 'in_progress'),
                                               (7, 160000, 85000, 'draft')]:
            start = monday + timedelta(days=offset)
            runs.append(make('cash.plan.run', {'name': 'DEMO — Week of %s' % start,
                'company_id': company.id, 'date_from': start, 'date_to': start + timedelta(days=6),
                'opening_balance': balance, 'budget_amount': budget, 'state': state,
                'notes': '<p>Fictional Odoo Beyond recording examples. No real bank execution.</p>'}))

        def document(partner, amount, age=0, purchase_line=None, customer=False, posted=True):
            kind = 'out_invoice' if customer else 'in_invoice'
            account = accounts['income' if customer else 'expense']
            line_vals = {'name': 'DEMO — Project supply / service', 'quantity': 1,
                         'price_unit': amount, 'account_id': account.id, 'tax_ids': [(5, 0, 0)]}
            if purchase_line:
                line_vals.update({'product_id': product.id, 'purchase_line_id': purchase_line.id})
            doc = make('account.move', {'move_type': kind, 'company_id': company.id,
                'partner_id': partner.id, 'journal_id': journals['sale' if customer else 'purchase'].id,
                'date': today, 'invoice_date': today - timedelta(days=max(age, 0)),
                'invoice_date_due': today - timedelta(days=age), 'invoice_payment_term_id': False,
                'ref': 'DEMO — recording sample', 'invoice_line_ids': [(0, 0, line_vals)]})
            if posted:
                doc.action_post()
            return doc

        bills = {}
        for key, amount, age in [('new', 24000, 105), ('update', 18000, 45), ('keep', 12000, 15),
                                 ('duplicate', 9000, 65), ('workflow', 12000, 25)]:
            bills[key] = document(partners[key], amount, age)
        # Include a second bill in a different aging bucket for one supplier.
        document(partners['new'], 6000, -10)
        invoices = [document(partners['customer'], 45000, 20, customer=True),
                    document(partners['customer2'], 22000, -7, customer=True)]

        def po(partner, amount, label):
            order = make('purchase.order', {'partner_id': partner.id, 'company_id': company.id,
                'currency_id': company.currency_id.id, 'date_order': fields.Datetime.now(),
                'partner_ref': 'DEMO — ' + label,
                'order_line': [(0, 0, {'name': 'DEMO — ' + label, 'product_id': product.id,
                    'product_qty': 1, 'product_uom': product.uom_po_id.id, 'price_unit': amount,
                    'date_planned': fields.Datetime.now(), 'taxes_id': [(5, 0, 0)]})]})
            order.button_confirm()
            if order.state == 'to approve':
                order.button_approve()
            if order.state not in ('purchase', 'done'):
                raise UserError(_('A custom PO approval rule prevented the demo PO from being confirmed. Complete its configuration before creating the examples.'))
            return order

        orders = [po(partners['po'], 40000, 'Unbilled equipment order'),
                  po(partners['po'], 25000, 'Unbilled site tools'),
                  po(partners['convert'], 16000, 'Fully invoiced steel order'),
                  po(partners['draft'], 11000, 'Draft vendor bill awaiting posting')]
        bills['convert'] = document(partners['convert'], 16000, 30, orders[2].order_line)
        document(partners['draft'], 11000, 0, orders[3].order_line, posted=False)

        def plan(label, amount, key='keep', flow='out', transaction='supplier', run=None,
                 decision='not_sent', approved=None, state=None, account=None, pos=None, docs=None, priority='1', funding='funded'):
            category_key = ({'customer': 'cat_in_customer', 'revenue': 'cat_in_sales',
                             'loan': 'cat_in_loan'}.get(transaction, 'cat_in_other') if flow == 'in' else
                            {'payroll': 'cat_out_payroll', 'expense': 'cat_out_rent',
                             'cash': 'cat_out_cash', 'transfer': 'cat_out_cash',
                             'loan': 'cat_out_loans', 'other': 'cat_out_other'}.get(transaction, 'cat_out_supplier'))
            category = self.env.ref('internal_transfer_voucher.' + category_key)
            vals = {'name': 'DEMO — ' + label, 'company_id': company.id, 'flow_type': flow,
                'transaction_type': transaction, 'category_id': category.id, 'partner_id': partners[key].id,
                'project_id': projects[len(registry.get('cash.plan.line', [])) % 2].id,
                'forecast_amount': amount, 'priority': priority, 'funding_status': funding,
                'journal_id': journals['bank'].id,
                'account_id': accounts[account or ('receivable' if flow == 'in' else 'payable')].id,
                'description': 'Fictional recording example. Seeded decisions are illustrative, not real approvals.'}
            if transaction == 'transfer':
                vals['destination_journal_id'] = journals['cash'].id
            if run:
                vals.update({'run_id': run.id, 'planned_date': max(run.date_from, min(today, run.date_to)),
                    'added_to_plan_on': fields.Datetime.now(), 'added_to_plan_by': self.env.user.id})
            if pos:
                vals['purchase_order_ids'] = [(6, 0, pos.ids)]
            if docs:
                vals['invoice_ids' if flow == 'in' else 'bill_ids'] = [(6, 0, docs.ids)]
            line = make('cash.plan.line', vals)
            if flow == 'out' and decision != 'not_sent':
                values = {'ceo_decision': decision, 'ceo_comment': 'SAMPLE decision for recording only.',
                          'approved_amount': (amount if approved is None else approved) if decision in ('approved', 'adjusted') else 0,
                          'state': state or ('approved' if decision in ('approved', 'adjusted') else
                                            'cancel' if decision == 'rejected' else 'planned')}
                line.write(values)
            return line

        # Real source-backed scenarios for the live review engine.
        plan('Update balance — old 25,000 / live 18,000', 25000, 'update', docs=bills['update'])
        plan('Keep — balance unchanged', 12000, 'keep', docs=bills['keep'])
        plan('Remove — no outstanding supplier balance', 7000, 'obsolete')
        plan('Primary supplier balance', 9000, 'duplicate', docs=bills['duplicate'])
        plan('Duplicate balance for agent review', 9000, 'duplicate')
        plan('Convert invoiced PO to supplier payable', 16000, 'convert', pos=orders[2])
        plan('Review — draft invoice not posted', 11000, 'draft', pos=orders[3])
        plan('Keep installment below remaining PO amount', 8000, 'po', pos=orders[1])

        plan('Awaiting CEO review — supplier installment', 8000, 'workflow', run=runs[1], decision='pending', priority='3')
        plan('Approved — ready for treasury', 6000, 'workflow', run=runs[1], decision='approved', priority='2')
        plan('Adjusted — release 4,000 of 7,000', 7000, 'workflow', run=runs[1], decision='adjusted', approved=4000, funding='partial')
        plan('On hold — awaiting delivery evidence', 3500, 'workflow', run=runs[1], decision='held', funding='unfunded')
        plan('Rejected — nonessential purchase', 2200, 'workflow', run=runs[1], decision='rejected')
        plan('Paid — accounting voucher to prepare', 5000, 'workflow', run=runs[1], decision='approved', state='executed')
        paid_draft = plan('Paid — draft voucher awaiting posting', 4200, 'workflow', run=runs[1], decision='approved', state='executed')
        settled = plan('Paid and posted — completed payment', 3000, 'workflow', run=runs[1], decision='approved', state='executed')
        for transaction, key, label, amount, account in [
            ('payroll', 'staff', 'Payroll and manpower', 28000, 'expense'),
            ('expense', 'landlord', 'Office rent', 6500, 'expense'),
            ('loan', 'bank', 'Financing installment', 4500, 'loan'),
            ('cash', 'staff', 'Site cash replenishment', 2000, 'expense'),
            ('transfer', 'bank', 'Bank to site cash allocation', 1500, 'cash'),
            ('other', 'staff', 'Employee reimbursement', 950, 'expense')]:
            plan(label, amount, key, transaction=transaction, run=runs[2], account=account)
        plan('Prior week — supplier payment deferred', 12500, 'workflow', run=runs[0], decision='held')
        plan('Prior week — expected collection not received', 18000, 'customer', flow='in', transaction='customer', run=runs[0])
        receipt = plan('Customer collection — confirmed', 15000, 'customer', flow='in', transaction='customer', run=runs[1], docs=invoices[0])
        receipt_draft = plan('Customer collection — draft receipt', 5000, 'customer2', flow='in', transaction='customer', run=runs[1], docs=invoices[1])
        plan('Next week project collection', 20000, 'customer', flow='in', transaction='customer', run=runs[2])
        plan('New financing inflow', 10000, 'bank', flow='in', transaction='loan', run=runs[2], account='loan')
        plan('Other revenue', 3000, 'customer2', flow='in', transaction='revenue', run=runs[2], account='income')
        plan('Receipt not yet assigned to a week', 2500, 'customer', flow='in', transaction='other')

        def voucher(label, amount, key, receipt=False, posted=False, method='bank_transfer', line=None,
                    docs=None, account=None, pos=None, fees=False):
            model = 'account.receipt.voucher' if receipt else 'account.payment.voucher'
            vals = {'date': today, 'company_id': company.id, 'currency_id': company.currency_id.id,
                'partner_id': partners[key].id, 'amount': amount,
                'journal_id': journals['cash' if method == 'cash' else 'bank'].id,
                'account_id': accounts[account or ('receivable' if receipt else 'payable')].id,
                'description': 'DEMO — ' + label, 'receipt_method' if receipt else 'payment_method': method}
            if line:
                vals['cash_plan_line_id'] = line.id
            if docs:
                vals['invoice_ids' if receipt else 'bill_ids'] = [(6, 0, docs.ids)]
            if pos:
                vals['purchase_order_ids'] = [(6, 0, pos.ids)]
                if len(pos) > 1:
                    vals['po_allocation_ids'] = [(0, 0, {'purchase_order_id': order.id, 'amount': amount / len(pos)}) for order in pos]
            if fees:
                vals.update({'has_bank_fees': True, 'fee_amount': 25, 'fee_account_id': accounts['expense'].id})
            record = make(model, vals, skip_cash_plan_autolink=bool(line))
            if line:
                link_vals = {'receipt_voucher_id' if receipt else 'payment_voucher_id': record.id}
                if receipt:
                    link_vals['state'] = 'executed'
                line.write(link_vals)
            if posted:
                record.action_post()
                if record.state != 'posted':
                    raise UserError(_('A demo voucher could not be posted. Review its accounting configuration.'))
                if docs:
                    if receipt:
                        record.action_reconcile_invoices()
                    else:
                        record.action_reconcile_bills()
            return record

        voucher('Draft from approved plan', 4200, 'workflow', line=paid_draft)
        voucher('Posted plan execution with fee', 3000, 'workflow', posted=True, line=settled, fees=True, docs=bills['workflow'])
        voucher('Customer partial collection', 15000, 'customer', receipt=True, posted=True, line=receipt, docs=invoices[0])
        voucher('Receipt awaiting accountant posting', 5000, 'customer2', receipt=True, line=receipt_draft, docs=invoices[1])
        voucher('Full bill settlement', 9000, 'duplicate', posted=True, docs=bills['duplicate'])
        voucher('Partial bill settlement', 4000, 'update', posted=True, docs=bills['update'])
        voucher('Supplier credit offset — awaiting allocation', 1500, 'new', posted=True)
        voucher('Supplier PO advance', 5000, 'po', posted=True, pos=orders[0], account='advance')
        voucher('One payment allocated to two POs', 6000, 'po', pos=orders[0] | orders[1], account='advance')
        voucher('Petty cash site expense', 750, 'staff', posted=True, method='cash', account='expense')
        voucher('Cheque awaiting issue', 1800, 'landlord', method='cheque', account='expense')
        cancelled = voucher('Cancelled duplicate draft', 1200, 'staff', method='cash', account='expense')
        cancelled.action_cancel()
        voucher('Cash sales collection', 850, 'customer2', receipt=True, posted=True, method='cash', account='income')
        voucher('Customer cheque awaiting deposit', 3200, 'customer', receipt=True, method='cheque')
        voucher('Full customer invoice collection', 22000, 'customer2', receipt=True, posted=True, docs=invoices[1])
        cancelled = voucher('Cancelled receipt draft', 400, 'customer', receipt=True, method='cash')
        cancelled.action_cancel()

        # Backfill registry with auto-created unplanned lines linked to our vouchers.
        for model in ('account.payment.voucher', 'account.receipt.voucher'):
            linked = self.env[model].browse(registry.get(model, [])).mapped('cash_plan_line_id')
            registry['cash.plan.line'] = sorted(set(registry.get('cash.plan.line', []) + linked.ids))
        review = make('cash.plan.review', {'name': 'DEMO — Live Payment Review', 'company_id': company.id, 'year': 'all'})
        self.env['cash.plan.line']._populate_payment_review(review)
        counts = [('Payment vouchers', 'account.payment.voucher'), ('Receipt vouchers', 'account.receipt.voucher'),
                  ('Weekly plans', 'cash.plan.run'), ('Planned / actual movements', 'cash.plan.line'),
                  ('Purchase orders', 'purchase.order'), ('Bills / customer invoices', 'account.move')]
        self.write({'records_json': registry, 'summary': '\n'.join('%s: %s' % (label, len(registry.get(model, [])))
                    for label, model in counts) + '\nReview recommendations: %s\nAll examples are fictional; seeded decisions are not real approvals.' % len(review.line_ids)})
