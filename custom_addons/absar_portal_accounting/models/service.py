"""Narrow portal gateway. No generic model/method/field names come from HTTP.

Portal groups deliberately receive no account.move/voucher/HR ACLs. Every
privileged operation below is preceded by actor, company, journal, record and
relation validation. sudo preserves the actor's uid for create_uid/audit.
"""
import math
from datetime import date
from odoo import api, fields, models, _, Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression
from odoo.tools import html2plaintext
from .accounting import _REVIEW_TOKEN

PREFIX = 'absar_portal_accounting.'
KINDS = {
    'bills': ('account.move', 'Vendor Bills', 'in_invoice'),
    'refunds': ('account.move', 'Vendor Credit Notes', 'in_refund'),
    'journals': ('account.move', 'Miscellaneous Entries', 'entry'),
    'payments': ('account.payment.voucher', 'Payment Vouchers', None),
    'receipts': ('account.receipt.voucher', 'Receipt Vouchers', None),
    'planned': ('cash.plan.line', 'Planned Payments', 'out'),
    'planned-receipts': ('cash.plan.line', 'Planned Receipts', 'in'),
}


class PortalAccountingService(models.AbstractModel):
    _name = 'absar.portal.accounting.service'
    _description = 'Employee portal accounting service'

    def _actor(self, role=None):
        user = self.env.user
        roles = {r: user.has_group(PREFIX + 'group_' + r) for r in ('preparer', 'approver', 'monitor', 'accountant')}
        roles['restricted'] = roles['preparer']
        roles['direct'] = roles['accountant'] and not roles['restricted']
        roles['preparer'] = roles['preparer'] or roles['accountant']
        if not user.active or user._is_public() or not any(roles.values()) or (role and not roles[role]):
            raise AccessError(_('You do not have access to this accounting operation.'))
        if user.has_group('employee_portal_suite.group_attendance_only'):
            raise AccessError(_('This account is restricted to attendance.'))
        if user.share and not user.sudo().with_company(user.company_id).employee_id:
            raise AccessError(_('An employee-linked portal account is required.'))
        return user, roles

    def _company(self, company_id):
        user, roles = self._actor()
        cid = self._id(company_id or user.company_id.id)
        company = user.sudo().company_ids.filtered(lambda c: c.id == cid)
        if not company:
            raise AccessError(_('Company is not permitted.'))
        return company

    def _env(self, company):
        return self.with_context(allowed_company_ids=[company.id]).with_company(company).sudo().env

    def _kind(self, kind):
        if kind not in KINDS:
            raise AccessError(_('Unsupported accounting area.'))
        return KINDS[kind]

    @staticmethod
    def _id(value):
        try:
            result = int(value)
            if isinstance(value, bool) or result <= 0 or str(result) != str(value):
                raise ValueError()
            return result
        except (TypeError, ValueError):
            raise ValidationError(_('Invalid record identifier.'))

    @staticmethod
    def _number(value, positive=False):
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            raise ValidationError(_('Enter a valid amount.'))
        if not math.isfinite(number) or (positive and number <= 0):
            raise ValidationError(_('Enter a finite, positive amount.'))
        return number

    def _relation(self, company, model, value, domain=None, required=False):
        if not value:
            if required:
                raise ValidationError(_('A required selection is missing.'))
            return self._env(company)[model].browse()
        rid = self._id(value)
        record = self._env(company)[model].search(expression.AND([[('id', '=', rid)], domain or []]), limit=1)
        if not record:
            raise AccessError(_('A selected record is not available in this company.'))
        return record

    def _journal(self, company, value, types=None, required=True):
        domain = [('company_id', '=', company.id), ('id', 'in', company.portal_accounting_journal_ids.ids)]
        if types:
            domain += [('type', 'in', types)]
        return self._relation(company, 'account.journal', value, domain, required)

    def _account(self, company, value, required=True):
        return self._relation(company, 'account.account', value,
                              [('company_ids', 'in', company.id), ('deprecated', '=', False)], required)

    def _partner(self, company, value, required=False):
        return self._relation(company, 'res.partner', value,
                              ['|', ('company_id', '=', False), ('company_id', '=', company.id)], required)

    def _date(self, value, required=True):
        if not value and not required:
            return False
        try:
            return fields.Date.to_date(value).isoformat()
        except (TypeError, ValueError, AttributeError):
            raise ValidationError(_('Enter a valid date.'))

    def _analytic(self, company, distribution):
        if not distribution:
            return {}
        if not isinstance(distribution, dict) or len(distribution) > 100:
            raise ValidationError(_('Invalid analytic distribution.'))
        result, totals = {}, {}
        for key, value in distribution.items():
            ids = [self._id(x) for x in str(key).split(',')]
            if len(ids)>20 or len(set(ids))!=len(ids):
                raise ValidationError(_('Invalid analytic combination.'))
            accounts = [self._relation(company, 'account.analytic.account', rid,
                ['|', ('company_id', '=', False), ('company_id', '=', company.id)], True) for rid in ids]
            plans = [account.plan_id.root_id.id for account in accounts]
            if len(plans)!=len(set(plans)):
                raise ValidationError(_('Use one analytic account per plan in each row.'))
            amount = self._number(value)
            if not 0 < amount <= 100:
                raise ValidationError(_('Analytic percentages must be greater than zero and at most 100.'))
            canonical = ','.join(map(str, sorted(ids)))
            if canonical in result:
                raise ValidationError(_('Combine duplicate allocation rows.'))
            result[canonical] = amount
            for plan in plans:
                totals[plan] = totals.get(plan,0)+amount
        if any(abs(total-100)>.01 for total in totals.values()):
            raise ValidationError(_('Each used analytic plan must total 100%.'))
        return result

    def _domain(self, company, kind):
        model, title, subtype = self._kind(kind)
        domain = [('company_id', '=', company.id)]
        if model == 'account.move':
            domain += [('move_type', '=', subtype), ('journal_id', 'in', company.portal_accounting_journal_ids.ids)]
        elif model == 'cash.plan.line':
            domain += [('flow_type', '=', subtype), '|', ('journal_id', '=', False),
                       ('journal_id', 'in', company.portal_accounting_journal_ids.ids)]
            # Empty configuration must never expose planning records either.
            if not company.portal_accounting_journal_ids:
                domain += [('id', '=', 0)]
        else:
            domain += [('journal_id', 'in', company.portal_accounting_journal_ids.ids)]
        return domain

    def _record(self, company, kind, record_id):
        model = self._kind(kind)[0]
        if not self.env.user.share:
            subtype = self._kind(kind)[2]
            domain = [('id','=',self._id(record_id)),('company_id','=',company.id)]
            if model == 'account.move':
                domain += [('move_type','=',subtype)]
            record = self.env[model].with_company(company).search(domain, limit=1)
            if not record:
                raise AccessError(_('Accounting record is unavailable.'))
            record.check_access('write')
            return record.sudo()
        record = self._env(company)[model].search(expression.AND([
            self._domain(company, kind), [('id', '=', self._id(record_id))]]), limit=1)
        if not record:
            raise AccessError(_('Accounting record is unavailable.'))
        return record

    def _list(self, company, kind, query='', status='', page=1):
        self._actor()
        model = self._kind(kind)[0]
        domain = self._domain(company, kind)
        if query:
            search_fields = ['name', 'partner_id.name'] if kind != 'journals' else ['name', 'ref']
            domain = expression.AND([domain, expression.OR([[(f, 'ilike', str(query)[:120])] for f in search_fields])])
        if status in ('draft', 'posted', 'cancel') and model != 'cash.plan.line':
            domain += [('state', '=', status)]
        elif status == 'submitted' and model != 'cash.plan.line':
            domain += [('portal_accounting_review', '=', 'submitted')]
        page = max(1, min(int(page or 1), 100000))
        records = self._env(company)[model].search(domain, order='id desc', limit=40, offset=(page-1)*40)
        return {'rows': [self._row(r, kind) for r in records],
                'count': self._env(company)[model].search_count(domain), 'page': page}

    def _row(self, record, kind):
        planned = record._name == 'cash.plan.line'
        return {'id': record.id, 'name': record.name or 'Draft',
                'partner': record.partner_id.display_name if kind != 'journals' else record.ref or '',
                'date': str((record.planned_date if planned else record.date) or ''),
                'journal': record.journal_id.display_name or '',
                'amount': record.forecast_amount if planned else (
                    record.amount_total if record._name == 'account.move' else record.amount),
                'currency': record.currency_id.name, 'state': record.state,
                'version': str(record.write_date),
                'review': record.ceo_decision if planned else (record.portal_accounting_review if record.portal_accounting_review_required else 'not_required'),
                'issuer': record.portal_accounting_issuer_id.name or record.create_uid.name}

    def _defaults(self, company, kind, partner_id=False):
        self._actor('preparer')
        self._kind(kind)
        journal_type = 'purchase' if kind in ('bills','refunds') else 'general' if kind == 'journals' else 'bank'
        journals = self._env(company)['account.journal'].search([
            ('id','in',company.portal_accounting_journal_ids.ids),('company_id','=',company.id),('type','=',journal_type)], order='sequence,id', limit=1)
        partner = self._partner(company, partner_id) if partner_id else self._env(company)['res.partner'].browse()
        currency = partner.with_company(company).property_purchase_currency_id if partner and kind in ('bills','refunds') else self._env(company)['res.currency'].browse()
        currency = currency or (journals.currency_id if kind in ('bills','refunds','journals') else self._env(company)['res.currency'].browse()) or company.currency_id
        term = partner.with_company(company).property_supplier_payment_term_id if partner else self._env(company)['account.payment.term'].browse()
        result = {'currency_id':currency.id, 'currency_name':currency.name, 'journal_id':journals.id or False,
                  'invoice_payment_term_id':term.id or False, 'selections':{}}
        for key, record in [('journal_id',journals),('currency_id',currency),('invoice_payment_term_id',term)]:
            result['selections'][key] = {'id':record.id or False,'name':record.display_name or ''}
        return result

    def _options(self, company, resource, query='', kind='bills', partner_id=False, offset=0, limit=30):
        self._actor()
        self._kind(kind)
        if not company.portal_accounting_journal_ids:
            raise AccessError(_('Configure portal accounting journals before using selections.'))
        cdom = ['|', ('company_id', '=', False), ('company_id', '=', company.id)]
        spec = {
            'partner': ('res.partner', cdom, 'display_name'),
            'account': ('account.account', [('company_ids', 'in', company.id), ('deprecated', '=', False)], 'display_name'),
            'product-category': ('product.category', [], 'display_name'),
            'product': ('product.product', cdom + [('purchase_ok', '=', True)], 'display_name'),
            'tax': ('account.tax', [('company_id', '=', company.id), ('type_tax_use', 'in', ['purchase', 'sale', 'none'] if kind == 'journals' else ['purchase', 'none'])], 'name'),
            'analytic': ('account.analytic.account', cdom, 'display_name'),
            'currency': ('res.currency', [('active', '=', True)], 'name'),
            'term': ('account.payment.term', cdom, 'name'),
            'uom': ('uom.uom', [('active', '=', True)], 'display_name'),
            'tax-grid': ('account.account.tag', [('applicability', '=', 'taxes'), '|',
                ('country_id', '=', False), ('country_id', '=', company.account_fiscal_country_id.id)], 'display_name'),
            'project': ('project.project', cdom, 'display_name'),
            'category': ('cash.plan.category', cdom + [('flow_type', '=', 'in' if kind == 'planned-receipts' else 'out')], 'name'),
            'run': ('cash.plan.run', [('company_id', '=', company.id), ('state', 'not in', ['done', 'cancel'])], 'name'),
            'journal': ('account.journal', [('company_id', '=', company.id), ('id', 'in', company.portal_accounting_journal_ids.ids)], 'display_name'),
            'po': ('purchase.order', [('company_id', '=', company.id), ('state', 'in', ['purchase', 'done'])], 'name'),
        }
        if resource in ('bill', 'invoice'):
            if resource == 'invoice' and kind not in ('receipts', 'planned-receipts'):
                raise AccessError(_('Customer invoices are available only for receipt matching.'))
            partner = self._partner(company, partner_id, True)
            spec[resource] = ('account.move', [('company_id', '=', company.id), ('partner_id', '=', partner.id),
                ('move_type', '=', 'in_invoice' if resource == 'bill' else 'out_invoice'),
                ('state', '=', 'posted'), ('amount_residual', '>', 0)], 'name')
        if resource == 'bank':
            partner = self._partner(company, partner_id, True)
            spec[resource] = ('res.partner.bank', [('partner_id', '=', partner.id)] + cdom, 'display_name')
        if resource not in spec:
            raise AccessError(_('Unsupported selection.'))
        model, domain, label = spec[resource]
        if resource in ('bill', 'invoice'):
            # Existing receivables can be matched without exposing their invoice forms.
            pass
        if resource == 'journal':
            if kind in ('bills', 'refunds'):
                domain += [('type', '=', 'purchase')]
            elif kind == 'journals':
                domain += [('type', '=', 'general')]
        if resource == 'po' and partner_id:
            partner = self._partner(company, partner_id, True)
            domain += [('partner_id', '=', partner.id)]
        if query:
            search_fields = {'account':['name','code'], 'product':['name','default_code','barcode'], 'partner':['name','ref','vat'], 'bank':['acc_number']}.get(resource,['name'])
            domain = expression.AND([domain, expression.OR([[(field,'ilike',str(query)[:120])] for field in search_fields])])
        offset = max(0,min(int(offset or 0),100000))
        limit = max(1,min(int(limit or 30),81))
        records = self._env(company)[model].search(domain, limit=limit, offset=offset, order='id')
        result = []
        for r in records:
            data = {'id': r.id, 'name': r[label]}
            if resource in ('bill', 'invoice'):
                data['name'] = '%s · %.2f %s outstanding' % (r.name, r.amount_residual, r.currency_id.name)
            if resource == 'analytic':
                data.update(plan=r.plan_id.root_id.display_name, plan_id=r.plan_id.root_id.id)
            if resource == 'product':
                data.update(self._product_selection(r, company))
            result.append(data)
        return result

    def _m2m(self, company, model, values, domain):
        if not isinstance(values, list) or len(values) > 100:
            raise ValidationError(_('Invalid selection list.'))
        records = self._env(company)[model].browse()
        for value in values:
            records |= self._relation(company, model, value, domain, True)
        return records

    def _analytic_name_map(self, company, distributions):
        ids = {int(part) for distribution in distributions for key in (distribution or {})
               for part in str(key).split(',') if part.isdigit() and int(part) > 0}
        accounts = self._env(company)['account.analytic.account'].search([
            ('id', 'in', sorted(ids)), '|', ('company_id', '=', False), ('company_id', '=', company.id)])
        return {str(account.id): account.display_name for account in accounts}

    def _analytic_label_map(self, company, distributions):
        ids = {int(part) for distribution in distributions for key in (distribution or {})
               for part in str(key).split(',') if part.isdigit() and int(part) > 0}
        accounts = self._env(company)['account.analytic.account'].search([
            ('id', 'in', sorted(ids)), '|', ('company_id', '=', False), ('company_id', '=', company.id)])
        return {str(a.id): {'id': a.id, 'label': a.display_name, 'plan': a.plan_id.root_id.display_name,
                            'plan_id': a.plan_id.root_id.id} for a in accounts}

    def _move_values(self, company, kind, data):
        subtype = self._kind(kind)[2]
        journal = self._journal(company, data.get('journal_id'), ['general'] if subtype == 'entry' else ['purchase'])
        partner = self._partner(company, data.get('partner_id'), subtype != 'entry')
        currency = self._relation(company, 'res.currency', data.get('currency_id') or company.currency_id.id,
                                  [('active', '=', True)], True)
        vals = {'move_type': subtype, 'journal_id': journal.id, 'company_id': company.id,
                'currency_id': currency.id, 'ref': str(data.get('ref') or '').strip()[:250],
                'payment_reference': str(data.get('payment_reference') or '')[:250],
                'date': self._date(data.get('date')), 'partner_id': partner.id or False}
        raw_lines = data.get('lines', [])
        if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= 200:
            raise ValidationError(_('Add between 1 and 200 lines.'))
        lines = []
        for row in raw_lines:
            if not isinstance(row, dict):
                raise ValidationError(_('Invalid entry line.'))
            display = row.get('display_type')
            if display in ('line_section', 'line_note') and subtype != 'entry':
                lines.append(Command.create({'display_type': display, 'name': str(row.get('name') or '')[:2000]}))
                continue
            account = self._account(company, row.get('account_id'))
            name = str(row.get('name') or '')[:2000]
            if not name:
                raise ValidationError(_('Enter a description on every line.'))
            line = {'account_id': account.id, 'name': name,
                    'analytic_distribution': self._analytic(company, row.get('analytic_distribution'))}
            if subtype == 'entry':
                debit, credit = self._number(row.get('debit')), self._number(row.get('credit'))
                if debit < 0 or credit < 0 or (debit and credit) or not (debit or credit):
                    raise ValidationError(_('Each journal line needs either a positive debit or a positive credit.'))
                line.update(debit=debit, credit=credit,
                            partner_id=self._partner(company, row.get('partner_id')).id or False,
                            date_maturity=self._date(row.get('date_maturity'), False))
                tags = self._m2m(company, 'account.account.tag', row.get('tax_tag_ids', []),
                    [('applicability', '=', 'taxes'), '|', ('country_id', '=', False),
                     ('country_id', '=', company.account_fiscal_country_id.id)])
                line['tax_tag_ids'] = [Command.set(tags.ids)]
                taxes = self._m2m(company, 'account.tax', row.get('taxes_id', []),
                    [('company_id', '=', company.id), ('type_tax_use', 'in', ['purchase', 'sale', 'none'])])
                line['tax_ids'] = [Command.set(taxes.ids)]
                if currency != company.currency_id:
                    line.update(currency_id=currency.id, amount_currency=self._number(row.get('amount_currency')))
            else:
                if account.account_type in ('asset_receivable', 'liability_payable'):
                    raise ValidationError(_('Use an expense or asset account on bill lines; Odoo creates the payable line.'))
                product = self._relation(company, 'product.product', row.get('product_id'),
                                         ['|', ('company_id', '=', False), ('company_id', '=', company.id)])
                taxes = self._m2m(company, 'account.tax', row.get('taxes_id', []),
                    [('company_id', '=', company.id), ('type_tax_use', 'in', ['purchase', 'none'])])
                discount = self._number(row.get('discount'))
                if not 0 <= discount <= 100:
                    raise ValidationError(_('Discount must be between 0 and 100.'))
                line.update(product_id=product.id or False, quantity=self._number(row.get('quantity'), True),
                            price_unit=self._number(row.get('price_unit')), discount=discount,
                            tax_ids=[Command.set(taxes.ids)])
                if row.get('product_uom_id'):
                    uom = self._relation(company, 'uom.uom', row['product_uom_id'],
                        [('category_id', '=', product.uom_id.category_id.id)] if product else [], True)
                    line['product_uom_id'] = uom.id
                po_line = self._relation(company, 'purchase.order.line', row.get('purchase_line_id'),
                    [('order_id.company_id', '=', company.id), ('order_id.partner_id', '=', partner.id),
                     ('order_id.state', 'in', ['purchase', 'done'])])
                if po_line:
                    if product != po_line.product_id:
                        raise ValidationError(_('PO line product does not match the bill line.'))
                    line['purchase_line_id'] = po_line.id
            lines.append(Command.create(line))
        if subtype == 'entry':
            balance = sum(command[2]['debit'] - command[2]['credit'] for command in lines)
            if not company.currency_id.is_zero(balance):
                raise ValidationError(_('Journal entry is not balanced.'))
            vals['line_ids'] = lines
        else:
            vals.update(invoice_date=self._date(data.get('invoice_date')), invoice_line_ids=lines,
                        invoice_payment_term_id=self._relation(company, 'account.payment.term', data.get('invoice_payment_term_id'),
                            ['|', ('company_id', '=', False), ('company_id', '=', company.id)]).id or False,
                        invoice_date_due=self._date(data.get('invoice_date_due'), False),
                        narration=str(data.get('narration') or '')[:10000],
                        payment_reference=str(data.get('payment_reference') or '')[:250],
                        partner_bank_id=self._relation(company, 'res.partner.bank', data.get('partner_bank_id'),
                            [('partner_id', '=', partner.id), '|', ('company_id', '=', False), ('company_id', '=', company.id)]).id or False)
        return vals

    def _voucher_values(self, company, kind, data):
        journal = self._journal(company, data.get('journal_id'))
        if not journal.default_account_id:
            raise ValidationError(_('The journal needs a default account.'))
        partner = self._partner(company, data.get('partner_id'), True)
        if self._id(data.get('currency_id') or company.currency_id.id) != company.currency_id.id:
            raise ValidationError(_('Your current voucher engine posts in company currency. Use company currency for portal vouchers.'))
        method_key = 'payment_method' if kind == 'payments' else 'receipt_method'
        method = data.get(method_key, 'cash')
        allowed = ['cash', 'cheque', 'bank_transfer'] + (['journal_transfer'] if kind == 'payments' else [])
        if method not in allowed:
            raise ValidationError(_('Invalid voucher method.'))
        account = self._account(company, data.get('account_id'), method != 'journal_transfer')
        vals = {'company_id': company.id, 'journal_id': journal.id, 'partner_id': partner.id,
                'amount': self._number(data.get('amount'), True), 'date': self._date(data.get('date')),
                'currency_id': self._relation(company, 'res.currency', data.get('currency_id') or company.currency_id.id,
                    [('active', '=', True)], True).id, 'account_id': account.id or False,
                method_key: method, 'description': str(data.get('description') or '')[:10000],
                'analytic_distribution': self._analytic(company, data.get('analytic_distribution'))}
        key = 'bill_ids' if kind == 'payments' else 'invoice_ids'
        selected = self._m2m(company, 'account.move', data.get(key, []),
            [('company_id', '=', company.id), ('partner_id', '=', partner.id), ('state', '=', 'posted'),
             ('move_type', '=', 'in_invoice' if kind == 'payments' else 'out_invoice')])
        vals[key] = [Command.set(selected.ids)]
        if kind == 'payments':
            pos = self._m2m(company, 'purchase.order', data.get('purchase_order_ids', []),
                [('company_id', '=', company.id), ('partner_id', '=', partner.id), ('state', 'in', ['purchase', 'done'])])
            vals['purchase_order_ids'] = [Command.set(pos.ids)]
            allocs = data.get('allocations', [])
            if not isinstance(allocs, list) or len(allocs) > 100:
                raise ValidationError(_('Invalid PO allocations.'))
            used = set()
            commands = []
            for row in allocs:
                rid = self._id(row.get('purchase_order_id'))
                if rid not in pos.ids or rid in used:
                    raise ValidationError(_('PO allocations must match the selected orders without duplicates.'))
                used.add(rid)
                commands.append(Command.create({'purchase_order_id': rid, 'amount': self._number(row.get('amount'), True)}))
            if len(pos) > 1 and used != set(pos.ids):
                raise ValidationError(_('Enter an allocation for every selected PO.'))
            vals['po_allocation_ids'] = commands
            destinations = data.get('destinations', [])
            if not isinstance(destinations, list) or len(destinations) > 100:
                raise ValidationError(_('Invalid destination journals.'))
            vals['line_ids'] = [Command.create({'journal_id': self._journal(company, r.get('journal_id')).id,
                                              'amount': self._number(r.get('amount'), True)}) for r in destinations]
            fee = bool(data.get('has_bank_fees'))
            vals.update(has_bank_fees=fee, fee_amount=self._number(data.get('fee_amount')) if fee else 0,
                        fee_account_id=self._account(company, data.get('fee_account_id'), fee).id if fee else False,
                        fee_tax_id=self._relation(company, 'account.tax', data.get('fee_tax_id'),
                            [('company_id', '=', company.id), ('type_tax_use', 'in', ['purchase', 'none'])]).id if fee else False,
                        fee_analytic_distribution=self._analytic(company, data.get('fee_analytic_distribution')) if fee else {})
        return vals

    def _plan_values(self, company, kind, data):
        flow = self._kind(kind)[2]
        partner = self._partner(company, data.get('partner_id'), True)
        transaction = data.get('transaction_type', 'supplier' if flow == 'out' else 'customer')
        valid = dict(self._env(company)['cash.plan.line']._fields['transaction_type'].selection)
        if transaction not in valid or str(data.get('priority', '1')) not in ('0', '1', '2', '3'):
            raise ValidationError(_('Invalid planning type or priority.'))
        funding = data.get('funding_status', 'funded')
        if funding not in ('funded', 'partial', 'unfunded'):
            raise ValidationError(_('Invalid funding status.'))
        category = self._relation(company, 'cash.plan.category', data.get('category_id'),
            [('flow_type', '=', flow), '|', ('company_id', '=', False), ('company_id', '=', company.id)], True)
        vals = {'name': str(data.get('name') or '')[:250] or _('Planned Cash Movement'),
                'company_id': company.id, 'flow_type': flow, 'partner_id': partner.id,
                'forecast_amount': self._number(data.get('forecast_amount'), True), 'category_id': category.id,
                'transaction_type': transaction, 'priority': str(data.get('priority', '1')), 'funding_status': funding,
                'journal_id': self._journal(company, data.get('journal_id'), required=False).id or False,
                'account_id': self._account(company, data.get('account_id'), False).id or False,
                'project_id': self._relation(company, 'project.project', data.get('project_id'),
                    ['|', ('company_id', '=', False), ('company_id', '=', company.id)]).id or False,
                'description': str(data.get('description') or '')[:10000]}
        pos = self._m2m(company, 'purchase.order', data.get('purchase_order_ids', []),
            [('company_id', '=', company.id), ('partner_id', '=', partner.id), ('state', 'in', ['purchase', 'done'])])
        vals['purchase_order_ids'] = [Command.set(pos.ids)]
        key = 'bill_ids' if flow == 'out' else 'invoice_ids'
        bills = self._m2m(company, 'account.move', data.get(key, []),
            [('company_id', '=', company.id), ('partner_id', '=', partner.id), ('state', '=', 'posted'),
             ('move_type', '=', 'in_invoice' if flow == 'out' else 'out_invoice')])
        vals[key] = [Command.set(bills.ids)]
        return vals

    def _save(self, company, kind, data):
        user, roles = self._actor('preparer')
        model = self._kind(kind)[0]
        if not company.portal_accounting_journal_ids:
            raise AccessError(_('Configure the company portal accounting journals first.'))
        vals = self._move_values(company, kind, data) if model == 'account.move' else (
            self._plan_values(company, kind, data) if model == 'cash.plan.line' else self._voucher_values(company, kind, data))
        record = self._record(company, kind, data['id']) if data.get('id') else False
        if record:
            record._portal_accounting_lock(data.get('version'))
            if model == 'cash.plan.line':
                if record.state != 'planned' or record.ceo_decision not in ('not_sent', 'not_required') or record.is_unplanned:
                    raise UserError(_('Submitted or executed planned movements cannot be edited.'))
            elif record.state != 'draft' or record.portal_accounting_review in ('submitted', 'approved'):
                raise UserError(_('Only an editable draft or returned document can be saved.'))
            # Restricted drafts remain with their preparer. Regular accountants can
            # collaborate on ordinary drafts within the permitted journals.
            if record.portal_accounting_issuer_id and record.portal_accounting_issuer_id != user and not (roles['direct'] and not record.portal_accounting_review_required):
                raise AccessError(_('This restricted draft belongs to another preparer.'))
            if model == 'account.move':
                line_key = 'line_ids' if kind == 'journals' else 'invoice_line_ids'
                vals[line_key] = [Command.clear()] + vals[line_key]
            if kind == 'payments':
                vals['line_ids'] = [Command.clear()] + vals['line_ids']
                vals['po_allocation_ids'] = [Command.clear()] + vals['po_allocation_ids']
            record.write(dict(vals, portal_accounting_review_required=record.portal_accounting_review_required or roles['restricted'], portal_accounting_review='draft', portal_accounting_reviewer_id=False,
                              portal_accounting_issuer_id=user.id))
        else:
            record = self._env(company)[model].create(dict(vals, portal_accounting_issuer_id=user.id, portal_accounting_review_required=roles['restricted']))
        self._audit(record, 'Saved draft', ', '.join(sorted(vals)))
        if data.get('post'):
            if not roles['direct'] or model == 'cash.plan.line':
                raise AccessError(_('Direct posting is not available to this user.'))
            self._act(company, kind, record.id, 'post', dict(data, version=str(record.write_date)))
        elif data.get('submit'):
            self._act(company, kind, record.id, 'submit', {'version': str(record.write_date)})
        return self._detail(company, kind, record.id)

    def _act(self, company, kind, record_id, action, data):
        user, roles = self._actor()
        record = self._record(company, kind, record_id)
        record._portal_accounting_lock(data.get('version'))
        planned = record._name == 'cash.plan.line'
        comment = str(data.get('comment') or '')[:2000]
        if planned:
            return self._plan_action(company, kind, record, action, data, user, roles)
        if action == 'submit':
            self._actor('preparer')
            if not record.portal_accounting_review_required or record.state != 'draft' or record.portal_accounting_review not in ('draft', 'returned'):
                raise UserError(_('Only restricted editable drafts can be submitted.'))
            if record.portal_accounting_issuer_id != user:
                raise AccessError(_('Only the preparer can submit this document.'))
            record.write({'portal_accounting_review': 'submitted', 'portal_accounting_comment': False})
        elif action in ('return', 'post'):
            if record.portal_accounting_review_required:
                self._actor('approver')
                if record.state != 'draft' or record.portal_accounting_review != 'submitted':
                    raise UserError(_('Only submitted drafts can be reviewed.'))
                if record.portal_accounting_issuer_id == user:
                    raise AccessError(_('Another accounting approver must review your document.'))
                if action == 'post':
                    record._portal_accounting_validate_submission()
            elif action != 'post' or not roles['direct'] or record.state != 'draft':
                raise AccessError(_('Direct posting is not permitted.'))
            if action == 'return':
                if not comment:
                    raise ValidationError(_('Enter a reason for returning the document.'))
                record.write({'portal_accounting_review': 'returned', 'portal_accounting_comment': comment,
                              'portal_accounting_reviewer_id': user.id})
            else:
                if kind in ('payments', 'receipts') and record.currency_id != company.currency_id:
                    raise ValidationError(_('Your current voucher engine posts in company currency. Return this voucher for correction before posting.'))
                if record._name == 'account.move':
                    warnings = '\n'.join(filter(None, [record.abnormal_amount_warning, record.abnormal_date_warning]))
                    if warnings and data.get('confirm_abnormal') is not True:
                        raise UserError(_('ACCOUNTING WARNING: %s. Review and acknowledge this warning before posting.') % warnings)
                if kind in ('bills', 'refunds') and record.ref:
                    self.env.cr.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',
                        ['absar-bill:%s:%s:%s:%s' % (company.id, record.partner_id.id, record.move_type, record.ref.strip().lower())])
                    self.env.cr.execute('''SELECT id FROM account_move
                        WHERE company_id=%s AND partner_id=%s AND move_type=%s
                        AND lower(btrim(ref))=lower(btrim(%s)) AND id!=%s AND state!='cancel' LIMIT 1''',
                        [company.id,record.partner_id.id,record.move_type,record.ref,record.id])
                    found=self.env.cr.fetchone()
                    duplicate=self._env(company)['account.move'].browse(found[0] if found else [])
                    if duplicate:
                        raise UserError(_('A bill/credit note with this vendor reference already exists: %s') % duplicate.display_name)
                record.write({'portal_accounting_review': 'approved' if record.portal_accounting_review_required else 'draft', 'portal_accounting_reviewer_id': user.id if record.portal_accounting_review_required else False,
                              'portal_accounting_comment': comment})
                result = record.with_context(_absar_accounting_token=_REVIEW_TOKEN, validate_analytic=True).action_post()
                if isinstance(result, dict) and result.get('res_model') == 'account.payment.voucher.overpayment.confirm':
                    wizard = self._env(company)[result['res_model']].browse(result['res_id'])
                    if data.get('confirm_overpayment') is True and wizard.voucher_id == record:
                        wizard.with_context(_absar_accounting_token=_REVIEW_TOKEN, validate_analytic=True).action_confirm()
                    else:
                        # Raising inside the controller's savepoint rolls review back.
                        raise UserError(_('PO OVERPAYMENT: %s. Review these amounts and explicitly confirm overpayment to continue.') % wizard.message)
                elif isinstance(result, dict) and result.get('res_model') == 'account.autopost.bills.wizard' and record.state == 'posted':
                    pass # Optional supplier automation suggestion; no supplier setting is changed.
                elif isinstance(result, dict) and result.get('type') == 'ir.actions.act_window':
                    raise UserError(_('An additional accounting wizard is required. Complete this operation internally.'))
                if record.state != 'posted':
                    raise UserError(_('The accounting method did not post this document.'))
        elif action in ('reconcile', 'unreconcile'):
            if not (roles['approver'] or roles['direct']):
                raise AccessError(_('Accounting posting permission is required.'))
            if kind not in ('payments', 'receipts') or record.state != 'posted':
                raise UserError(_('Only posted vouchers can be reconciled.'))
            method = ('action_reconcile_bills' if kind == 'payments' else 'action_reconcile_invoices') if action == 'reconcile' else (
                'action_unreconcile_bills' if kind == 'payments' else 'action_unreconcile_invoices')
            getattr(record, method)()
        elif action in ('reset', 'request-reset'):
            if not (roles['preparer'] or roles['approver']):
                raise AccessError(_('Accounting access is required.'))
            if record.state not in ('posted', 'cancel') or not comment:
                raise UserError(_('Enter a reason for requesting a reset.'))
            if record.portal_accounting_reset_pending:
                raise UserError(_('A reset request is already pending.'))
            # Vouchers deliberately reject business writes after posting. These
            # three administrative fields do not modify accounting amounts/state.
            models.Model.write(record, {'portal_accounting_reset_pending': True,
                          'portal_accounting_reset_requested_by': user.id,
                          'portal_accounting_reset_reason': comment})
            managers = self._env(company)['res.users'].search([('active','=',True),('share','=',False),
                ('company_ids','in',company.id),('groups_id','in',self.env.ref('account.group_account_manager').id)])
            for manager in managers:
                record.activity_schedule('mail.mail_activity_data_todo', user_id=manager.id,
                    summary=_('Reset to Draft permission requested'), note=comment)
            action = 'Requested Reset to Draft (document remains posted/cancelled)'
        elif action == 'cancel':
            self._actor('preparer')
            if record.state != 'draft' or record.portal_accounting_review not in ('draft', 'returned') or (record.portal_accounting_issuer_id != user and not (roles['direct'] and not record.portal_accounting_review_required)):
                raise AccessError(_('Only an authorized preparer can cancel this draft.'))
            getattr(record, 'button_cancel' if record._name == 'account.move' else 'action_cancel')()
        elif action == 'find':
            self._actor('preparer')
            if kind not in ('payments', 'receipts') or record.state != 'draft' or record.portal_accounting_review not in ('draft', 'returned'):
                raise UserError(_('Find matching documents on an editable draft voucher.'))
            if record.portal_accounting_issuer_id != user and not (roles['direct'] and not record.portal_accounting_review_required):
                raise AccessError(_('Only the preparer may change selected documents.'))
            getattr(record, 'action_find_matching_bills' if kind == 'payments' else 'action_find_matching_invoices')()
        else:
            raise AccessError(_('Unsupported accounting action.'))
        if action in ('return', 'post') and record.portal_accounting_review_required:
            record._portal_accounting_notify(record.portal_accounting_issuer_id,
                _('Accounting document %s: %s') % (record.display_name, _('Posted') if action == 'post' else _('Returned for correction')),
                _('%(user)s: %(comment)s', user=user.name, comment=comment or _('Review completed.')))
        self._audit(record, action, comment)
        return self._detail(company, kind, record.id)

    def _audit(self, record, action, detail=''):
        user = self.env.user
        record.message_post(body=_('Accounting: %(action)s by %(user)s. %(detail)s',
            action=action, user=user.name, detail=detail), message_type='comment',
            subtype_xmlid='mail.mt_note', author_id=user.partner_id.id,
            email_from=user.email_formatted or record.company_id.partner_id.email_formatted or 'Accounting <noreply@localhost>')

    def _plan_action(self, company, kind, record, action, data, user, roles):
        if action == 'request-reset':
            self._actor('preparer')
            if record.portal_accounting_issuer_id and record.portal_accounting_issuer_id != user:
                raise AccessError(_('Only the preparer can request a reset.'))
            record.action_reset_to_draft()
        elif action == 'submit':
            self._actor('preparer')
            if record.portal_accounting_issuer_id and record.portal_accounting_issuer_id != user:
                raise AccessError(_('Only the preparer can submit this movement.'))
            record.action_submit_to_ceo()
        elif action in ('approve', 'hold', 'reject', 'add-plan'):
            if not user.has_group('employee_portal_suite.group_employee_portal_ceo'):
                raise AccessError(_('The existing CEO role is required for payment decisions.'))
            if action == 'add-plan':
                if record.run_id or record.state == 'cancel':
                    raise UserError(_('This movement cannot be added to a weekly plan.'))
                run = self._relation(company, 'cash.plan.run', data.get('run_id'),
                    [('company_id', '=', company.id), ('state', 'not in', ['done', 'cancel'])], True)
                record._assign_to_weekly_plan(run, added_by=user)
            else:
                record.action_ceo_decide({'approve': 'approved', 'hold': 'held', 'reject': 'rejected'}[action],
                    approved_amount=self._number(data.get('approved_amount'), True) if action == 'approve' else None,
                    comment=str(data.get('comment') or '')[:2000], reviewer=user)
        elif action == 'create-voucher':
            self._actor('preparer')
            if kind == 'planned':
                result = record.action_create_payment_voucher()
                target_kind, voucher = 'payments', record.payment_voucher_id
            else:
                result = record.action_create_receipt_voucher()
                target_kind, voucher = 'receipts', record.receipt_voucher_id
            if not voucher:
                raise UserError(_('No voucher was created.'))
            self._journal(company, voucher.journal_id.id)
            if not voucher.portal_accounting_issuer_id:
                voucher.write({'portal_accounting_issuer_id': user.id, 'portal_accounting_review_required': roles['restricted']})
            return {'redirect': '/my/employee/accounting/%s/%s?company_id=%s' % (target_kind, voucher.id, company.id)}
        else:
            raise AccessError(_('This planning action is not available. Payment execution remains with the existing internal execution managers.'))
        return self._detail(company, kind, record.id)

    def _submit_selected(self, company, selections):
        user, roles = self._actor('preparer')
        if not isinstance(selections, list) or not 1 <= len(selections) <= 100:
            raise ValidationError(_('Select between 1 and 100 planned payments.'))
        seen = set()
        records = self._env(company)['cash.plan.line'].browse()
        for selection in sorted(selections, key=lambda row: self._id(row.get('id'))):
            rid = self._id(selection.get('id'))
            if rid in seen:
                raise ValidationError(_('Duplicate selection.'))
            seen.add(rid)
            record = self._record(company, 'planned', rid)
            record._portal_accounting_lock(selection.get('version'))
            if record.portal_accounting_issuer_id and record.portal_accounting_issuer_id != user:
                raise AccessError(_('A selected planned payment belongs to another preparer.'))
            records |= record
        records.action_submit_selected_to_ceo()
        return len(records)

    def _detail(self, company, kind, record_id=None):
        user, roles = self._actor()
        model, title, subtype = self._kind(kind)
        record = self._record(company, kind, record_id) if record_id else False
        data = {'id': record.id if record else 0, 'company_id': company.id, 'kind': kind,
                'company_currency_name': company.currency_id.name, 'analytic_names': {}, 'analytic_labels': {},
                'currency_id': company.currency_id.id, 'currency_name': company.currency_id.name,
                'date': fields.Date.context_today(self).isoformat(), 'invoice_date': fields.Date.context_today(self).isoformat(),
                'lines': [], 'bill_ids': [], 'invoice_ids': [], 'purchase_order_ids': [], 'allocations': [], 'destinations': [],
                'selections': {}, 'roles': roles, 'state': 'draft', 'review': 'draft', 'name': 'New',
                'version': '', 'editable': roles['preparer'], 'can_review': False, 'can_post': roles['direct'], 'review_required':roles['restricted'],
                'is_ceo': user.has_group('employee_portal_suite.group_employee_portal_ceo'), 'attachments': []}
        if not record:
            if roles['preparer']:
                defaults=self._defaults(company,kind)
                data.update(defaults)
            return data
        data.update(self._row(record, kind), version=str(record.write_date),
                    review=record.ceo_decision if model == 'cash.plan.line' else (record.portal_accounting_review if record.portal_accounting_review_required else 'not_required'),
                    review_required=record.portal_accounting_review_required,
                    comment=record.portal_accounting_comment or '', issuer_id=record.portal_accounting_issuer_id.id)
        data['editable'] = roles['preparer'] and (not record.portal_accounting_issuer_id or record.portal_accounting_issuer_id == user or (roles['direct'] and not record.portal_accounting_review_required)) and (
            record.state == 'planned' and record.ceo_decision in ('not_sent', 'not_required') and not record.is_unplanned if model == 'cash.plan.line'
            else record.state == 'draft' and record.portal_accounting_review in ('draft', 'returned'))
        data['can_post'] = roles['direct'] and data['editable'] and not record.portal_accounting_review_required
        data['can_review'] = record.portal_accounting_review_required and roles['approver'] and record.portal_accounting_issuer_id != user and (
            record.state == 'draft' and record.portal_accounting_review == 'submitted')
        scalar_fields = ['ref', 'payment_reference', 'invoice_date', 'invoice_date_due', 'narration', 'description', 'payment_method', 'receipt_method',
                         'amount', 'forecast_amount', 'transaction_type', 'priority', 'funding_status', 'analytic_distribution',
                         'has_bank_fees', 'fee_amount', 'fee_analytic_distribution', 'approved_amount', 'actual_amount',
                         'ceo_comment', 'planned_date', 'allocated_amount', 'remaining_to_reconcile']
        scalar_fields += ['reset_request_pending', 'portal_accounting_reset_pending']
        for name in scalar_fields:
            if name in record._fields:
                value = record[name]
                data[name] = str(value) if isinstance(value, date) else value
        for name in ('partner_id', 'journal_id', 'account_id', 'currency_id', 'invoice_payment_term_id',
                     'project_id', 'category_id', 'run_id', 'fee_account_id', 'fee_tax_id', 'partner_bank_id'):
            if name in record._fields:
                value = record[name]
                data[name] = value.id or False
                data['selections'][name] = {'id': value.id, 'name': value.display_name or ''}
        data['currency_name'] = record.currency_id.name
        for name in ('bill_ids', 'invoice_ids', 'purchase_order_ids'):
            if name in record._fields:
                data[name] = record[name].ids
                data['selections'][name] = [{'id': r.id, 'name': r.display_name} for r in record[name]]
        distributions = record.line_ids.mapped('analytic_distribution') if model == 'account.move' else [data.get('analytic_distribution'), data.get('fee_analytic_distribution')]
        data['analytic_labels'] = self._analytic_label_map(company, distributions)
        data['analytic_names'] = {key: value['label'] for key, value in data['analytic_labels'].items()}
        if model == 'account.move':
            data['warnings'] = '\n'.join(filter(None, [record.abnormal_amount_warning, record.abnormal_date_warning]))
            lines = record.line_ids if kind == 'journals' else record.invoice_line_ids
            for line in lines:
                row = {'name': line.name or '', 'account_id': line.account_id.id, 'account_name': line.account_id.display_name or '',
                       'product_id': line.product_id.id, 'product_name': line.product_id.display_name or '',
                       'product_uom_id': line.product_uom_id.id, 'uom_name': line.product_uom_id.display_name or '',
                       'partner_id': line.partner_id.id, 'partner_name': line.partner_id.display_name or '',
                       'quantity': line.quantity, 'price_unit': line.price_unit, 'discount': line.discount,
                       'debit': line.debit, 'credit': line.credit, 'amount_currency': line.amount_currency,
                       'display_type': line.display_type, 'date_maturity': str(line.date_maturity or ''),
                       'analytic_distribution': line.analytic_distribution or {}, 'taxes_id': line.tax_ids.ids,
                       'tax_names': [{'id': t.id, 'name': t.name} for t in line.tax_ids],
                       'tax_tag_ids': line.tax_tag_ids.ids,
                       'grid_names': [{'id': t.id, 'name': t.display_name} for t in line.tax_tag_ids],
                       'purchase_line_id': line.purchase_line_id.id, 'subtotal': line.price_subtotal}
                data['lines'].append(row)
            data.update(untaxed=record.amount_untaxed, tax=record.amount_tax, total=record.amount_total,
                        balance_due=record.amount_residual,
                        journal_items=[{'account': l.account_id.display_name, 'partner': l.partner_id.display_name,
                                        'name': l.name or '', 'debit': l.debit, 'credit': l.credit,
                                        'analytic_distribution': l.analytic_distribution or {},
                                        'tax_names': [{'id': t.id, 'name': t.name} for t in l.tax_ids],
                                        'grid_names': [{'id': t.id, 'name': t.display_name} for t in l.tax_tag_ids]} for l in record.line_ids])
        if kind == 'payments':
            data['allocations'] = [{'purchase_order_id': r.purchase_order_id.id, 'name': r.purchase_order_id.display_name,
                                    'amount': r.amount} for r in record.po_allocation_ids]
            data['destinations'] = [{'journal_id': r.journal_id.id, 'name': r.journal_id.display_name,
                                    'amount': r.amount} for r in record.line_ids]
        attachments = self._env(company)['ir.attachment'].search([
            ('res_model', '=', model), ('res_id', '=', record.id), ('type', '=', 'binary')], limit=100)
        data['attachments'] = [{'id': a.id, 'name': a.name} for a in attachments]
        data['history'] = [{'date':str(m.date), 'author':m.author_id.name or '', 'body':html2plaintext(m.body)} for m in record.message_ids.sorted('id',reverse=True)[:100]]
        return data

    def _create_bill_from_po(self, company, po_id, version):
        user,roles=self._actor('preparer')
        if not user.has_group('absar_portal_purchase_monitor.group_portal_purchase_user'):
            raise AccessError(_('The Purchase User working role is required to create vendor bills from orders.'))
        po=self._relation(company,'purchase.order',po_id,[('company_id','=',company.id),('state','in',['purchase','done'])],True)
        po._portal_lock()
        if str(po.write_date)!=version:
            raise UserError(_('This purchase order changed. Reload it before creating a bill.'))
        defaults=self._defaults(company,'bills',po.partner_id.id)
        journal=self._journal(company,defaults['journal_id'],['purchase'])
        before=po.invoice_ids
        po.with_context(default_journal_id=journal.id,allowed_company_ids=[company.id]).action_create_invoice()
        po.invalidate_recordset()
        created=po.invoice_ids-before
        if len(created)!=1 or created.move_type!='in_invoice':
            raise UserError(_('Expected one native draft vendor bill. No bill was created.'))
        self._journal(company,created.journal_id.id,['purchase'])
        created.write({'portal_accounting_issuer_id':user.id,'portal_accounting_review_required':roles['restricted']})
        self._audit(created,'Created draft vendor bill from purchase order',po.name)
        return {'url':'/my/employee/accounting/bills/%s?company_id=%s'%(created.id,company.id)}

    def _po_lines(self, company, po_id):
        self._actor('preparer')
        po = self._relation(company, 'purchase.order', po_id,
            [('company_id', '=', company.id), ('state', 'in', ['purchase', 'done'])], True)
        data = {'analytic_labels': self._analytic_label_map(company, po.order_line.mapped('analytic_distribution')),
                'analytic_names': self._analytic_name_map(company, po.order_line.mapped('analytic_distribution')),
                'partner_id': po.partner_id.id, 'partner_name': po.partner_id.display_name,
                'currency_id': po.currency_id.id, 'currency_name': po.currency_id.name, 'ref': po.partner_ref or '', 'lines': []}
        for line in po.order_line:
            if line.display_type:
                data['lines'].append({'display_type': line.display_type, 'name': line.name})
            elif line.qty_to_invoice > 0:
                native = line._prepare_account_move_line()
                account = line.product_id.product_tmpl_id.get_product_accounts(fiscal_pos=po.fiscal_position_id).get('expense')
                data['lines'].append({'name': native.get('name') or line.name, 'product_id': line.product_id.id,
                    'product_name': line.product_id.display_name, 'quantity': native.get('quantity', line.qty_to_invoice),
                    'product_uom_id': line.product_uom.id, 'uom_name': line.product_uom.display_name,
                    'price_unit': native.get('price_unit', line.price_unit), 'discount': native.get('discount', line.discount),
                    'purchase_line_id': line.id, 'account_id': account.id if account else False,
                    'account_name': account.display_name if account else '', 'taxes_id': line.taxes_id.ids,
                    'tax_names': [{'id': t.id, 'name': t.name} for t in line.taxes_id],
                    'analytic_distribution': line.analytic_distribution or {}})
        if not any(not r.get('display_type') for r in data['lines']):
            raise UserError(_('This PO has no quantity ready to bill. Check its bill control policy and receipts.'))
        return data

    def _preview(self, company, kind, data):
        self._actor('preparer')
        if kind not in ('bills', 'refunds', 'journals'):
            raise AccessError(_('Preview is available for bills and journal entries.'))
        data = dict(data)
        defaults = self._defaults(company,kind,data.get('partner_id'))
        for key in ('journal_id','currency_id'):
            if not data.get(key):data[key]=defaults[key]
        if not data.get('journal_id'):
            raise ValidationError(_('Select an available journal of the correct type in Accounting Settings.'))
        vals = self._move_values(company, kind, data)
        class PreviewRollback(Exception):
            pass
        result = None
        try:
            with self.env.cr.savepoint():
                record = self._env(company)['account.move'].with_context(
                    tracking_disable=True, mail_create_nolog=True, mail_create_nosubscribe=True).create(vals)
                result = {'untaxed': record.amount_untaxed, 'tax': record.amount_tax,
                          'total': record.amount_total, 'currency': record.currency_id.name,
                          'line_amounts': record.invoice_line_ids.mapped('price_subtotal') if kind != 'journals' else [],
                          'journal_items': [{'account': l.account_id.display_name, 'partner': l.partner_id.display_name,
                                             'name': l.name or '', 'debit': l.debit, 'credit': l.credit,
                                             'analytic_distribution': l.analytic_distribution or {},
                                             'tax_names': [{'id': t.id, 'name': t.name} for t in l.tax_ids],
                                             'grid_names': [{'id': t.id, 'name': t.display_name} for t in l.tax_tag_ids]} for l in record.line_ids]}
                raise PreviewRollback()
        except PreviewRollback:
            pass
        return result
