"""Narrow portal gateway. No generic model/method/field names come from HTTP.

Portal groups deliberately receive no account.move or HR ACLs. Every
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
PREFIX = 'portal_backend_workspace.accounting__'
KINDS = {'invoices': ('account.move', 'Customer Invoices', 'out_invoice'), 'bills': ('account.move', 'Vendor Bills', 'in_invoice'), 'refunds': ('account.move', 'Vendor Credit Notes', 'in_refund'), 'journals': ('account.move', 'Miscellaneous Entries', 'entry')}

class PortalAccountingService(models.AbstractModel):
    _name = 'pbw.portal.accounting.service'
    _description = 'Employee portal accounting service'

    def _actor(self, role=None, kind=None):
        user = self.env.user
        roles = {r: user.has_group(PREFIX + 'group_' + r) for r in ('preparer', 'approver', 'monitor', 'accountant', 'customer_invoicing')}
        roles['restricted'] = roles['preparer']
        roles['direct'] = (roles['accountant'] or (kind == 'invoices' and roles['customer_invoicing'])) and (not roles['restricted'])
        roles['preparer'] = roles['preparer'] or roles['accountant'] or (kind == 'invoices' and roles['customer_invoicing'])
        if not user.active or user._is_public() or (not any(roles.values())) or (role and (not roles[role])):
            raise AccessError(_('You do not have access to this accounting operation.'))
        if user.share and (not user.sudo().with_company(user.company_id).employee_id):
            raise AccessError(_('An employee-linked portal account is required.'))
        return (user, roles)

    def _company(self, company_id):
        user, roles = self._actor()
        cid = self._id(company_id or user.company_id.id)
        company = user.sudo().company_ids.filtered(lambda c: c.id == cid)
        if not company:
            raise AccessError(_('Company is not permitted.'))
        return company

    def _env(self, company):
        return self.with_context(allowed_company_ids=[company.id]).with_company(company).sudo().env

    def _kinds(self):
        user, roles = self._actor()
        return {key: value for key, value in KINDS.items() if (roles['customer_invoicing'] if key == 'invoices' else any((user.has_group(PREFIX + 'group_' + role) for role in ('preparer', 'approver', 'monitor', 'accountant'))))}

    def _kind(self, kind):
        if kind not in KINDS or kind not in self._kinds():
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

    def _journal_ids(self, company, kind=None):
        if kind == 'invoices':
            self._kind('invoices')
            return self._env(company)['account.journal'].with_context(active_test=False).search([('company_id', '=', company.id), ('type', '=', 'sale')]).ids
        return company.pbw_accounting_journal_ids.ids

    def _workspace_configured(self, company, kind=None):
        if kind == 'invoices':
            return bool(self._journal_ids(company, kind))
        if kind is None and self._actor()[1]['customer_invoicing']:
            return bool(company.pbw_accounting_journal_ids or self._journal_ids(company, 'invoices'))
        return bool(company.pbw_accounting_journal_ids)

    def _journal(self, company, value, types=None, required=True, kind=None):
        domain = [('company_id', '=', company.id), ('id', 'in', self._journal_ids(company, kind))]
        if types:
            domain += [('type', 'in', types)]
        return self._relation(company, 'account.journal', value, domain, required)

    def _account(self, company, value, required=True):
        return self._relation(company, 'account.account', value, [('company_ids', 'in', company.id), ('deprecated', '=', False)], required)

    def _partner(self, company, value, required=False):
        return self._relation(company, 'res.partner', value, ['|', ('company_id', '=', False), ('company_id', '=', company.id)], required)

    def _date(self, value, required=True):
        if not value and (not required):
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
        result, totals = ({}, {})
        for key, value in distribution.items():
            ids = [self._id(x) for x in str(key).split(',')]
            if len(ids) > 20 or len(set(ids)) != len(ids):
                raise ValidationError(_('Invalid analytic combination.'))
            accounts = [self._relation(company, 'account.analytic.account', rid, ['|', ('company_id', '=', False), ('company_id', '=', company.id)], True) for rid in ids]
            plans = [account.plan_id.root_id.id for account in accounts]
            if len(plans) != len(set(plans)):
                raise ValidationError(_('Use one analytic account per plan in each row.'))
            amount = self._number(value)
            if not 0 < amount <= 100:
                raise ValidationError(_('Analytic percentages must be greater than zero and at most 100.'))
            canonical = ','.join(map(str, sorted(ids)))
            if canonical in result:
                raise ValidationError(_('Combine duplicate allocation rows.'))
            result[canonical] = amount
            for plan in plans:
                totals[plan] = totals.get(plan, 0) + amount
        if any((abs(total - 100) > 0.01 for total in totals.values())):
            raise ValidationError(_('Each used analytic plan must total 100%.'))
        return result

    def _domain(self, company, kind):
        model, title, subtype = self._kind(kind)
        domain = [('company_id', '=', company.id)]
        domain += [('move_type', '=', subtype), ('journal_id', 'in', self._journal_ids(company, kind))]
        return domain

    def _record(self, company, kind, record_id):
        model = self._kind(kind)[0]
        if not self.env.user.share:
            subtype = self._kind(kind)[2]
            domain = [('id', '=', self._id(record_id)), ('company_id', '=', company.id)]
            domain += [('move_type', '=', subtype)]
            record = self.env[model].with_company(company).search(domain, limit=1)
            if not record:
                raise AccessError(_('Accounting record is unavailable.'))
            record.check_access('write')
            return record.sudo()
        record = self._env(company)[model].search(expression.AND([self._domain(company, kind), [('id', '=', self._id(record_id))]]), limit=1)
        if not record:
            raise AccessError(_('Accounting record is unavailable.'))
        return record

    def _list(self, company, kind, query='', status='', page=1):
        self._actor(kind=kind)
        model = self._kind(kind)[0]
        domain = self._domain(company, kind)
        if query:
            search_fields = ['name', 'partner_id.name'] if kind != 'journals' else ['name', 'ref']
            domain = expression.AND([domain, expression.OR([[(f, 'ilike', str(query)[:120])] for f in search_fields])])
        if status in ('draft', 'posted', 'cancel'):
            domain += [('state', '=', status)]
        elif status == 'submitted':
            domain += [('pbw_accounting_review', '=', 'submitted')]
        page = max(1, min(int(page or 1), 100000))
        records = self._env(company)[model].search(domain, order='id desc', limit=40, offset=(page - 1) * 40)
        return {'rows': [self._row(r, kind) for r in records], 'count': self._env(company)[model].search_count(domain), 'page': page}

    def _row(self, record, kind):
        return {'id': record.id, 'name': record.name or 'Draft', 'partner': record.partner_id.display_name if kind != 'journals' else record.ref or '', 'date': str((record.date) or ''), 'journal': record.journal_id.display_name or '', 'amount': record.amount_total, 'currency': record.currency_id.name, 'state': record.state, 'version': str(record.write_date), 'review': record.pbw_accounting_review if record.pbw_accounting_review_required else 'not_required', 'issuer': record.pbw_accounting_issuer_id.name or record.create_uid.name}

    def _defaults(self, company, kind, partner_id=False):
        self._actor('preparer', kind=kind)
        self._kind(kind)
        journal_type = 'sale' if kind == 'invoices' else 'purchase' if kind in ('bills', 'refunds') else 'general' if kind == 'journals' else 'bank'
        journals = self._env(company)['account.journal'].search([('id', 'in', self._journal_ids(company, kind)), ('company_id', '=', company.id), ('type', '=', journal_type)], order='sequence,id', limit=1)
        partner = self._partner(company, partner_id) if partner_id else self._env(company)['res.partner'].browse()
        currency = partner.with_company(company).property_purchase_currency_id if partner and kind in ('bills', 'refunds') else self._env(company)['res.currency'].browse()
        currency = currency or journals.currency_id or company.currency_id
        term = (partner.with_company(company).property_payment_term_id if kind == 'invoices' else partner.with_company(company).property_supplier_payment_term_id) if partner else self._env(company)['account.payment.term'].browse()
        result = {'currency_id': currency.id, 'currency_name': currency.name, 'journal_id': journals.id, 'invoice_payment_term_id': term.id, 'selections': {}}
        for key, record in [('journal_id', journals), ('currency_id', currency), ('invoice_payment_term_id', term)]:
            result['selections'][key] = {'id': record.id, 'name': record.display_name or ''}
        return result

    def _options(self, company, resource, query='', kind='bills', partner_id=False, offset=0, limit=30):
        self._actor(kind=kind)
        self._kind(kind)
        if kind != 'invoices' and (not company.pbw_accounting_journal_ids):
            raise AccessError(_('Configure portal accounting journals before using selections.'))
        cdom = ['|', ('company_id', '=', False), ('company_id', '=', company.id)]
        if kind == 'invoices' and resource not in ('partner', 'account', 'product', 'product-category', 'tax', 'analytic', 'currency', 'term', 'uom', 'tax-grid', 'project', 'journal', 'bank'):
            raise AccessError(_('This selection is not available for customer invoicing.'))
        spec = {'partner': ('res.partner', cdom, 'display_name'), 'account': ('account.account', [('company_ids', 'in', company.id), ('deprecated', '=', False)], 'display_name'), 'product-category': ('product.category', [], 'display_name'), 'product': ('product.product', cdom + [('sale_ok' if kind == 'invoices' else 'purchase_ok', '=', True)], 'display_name'), 'tax': ('account.tax', [('company_id', '=', company.id), ('type_tax_use', 'in', ['purchase', 'sale', 'none'] if kind == 'journals' else ['sale', 'none'] if kind == 'invoices' else ['purchase', 'none'])], 'name'), 'analytic': ('account.analytic.account', cdom, 'display_name'), 'currency': ('res.currency', [('active', '=', True)], 'name'), 'term': ('account.payment.term', cdom, 'name'), 'uom': ('uom.uom', [('active', '=', True)], 'display_name'), 'tax-grid': ('account.account.tag', [('applicability', '=', 'taxes'), '|', ('country_id', '=', False), ('country_id', '=', company.account_fiscal_country_id.id)], 'display_name'), 'project': ('project.project', cdom, 'display_name'), 'journal': ('account.journal', [('company_id', '=', company.id), ('id', 'in', self._journal_ids(company, kind))], 'display_name'), 'po': ('purchase.order', [('company_id', '=', company.id), ('state', 'in', ['purchase', 'done'])], 'name')}
        if resource in ('bill', 'invoice'):
            if resource == 'invoice':
                raise AccessError(_('Customer invoices are available only for receipt matching.'))
            partner = self._partner(company, partner_id, True)
            spec[resource] = ('account.move', [('company_id', '=', company.id), ('partner_id', '=', partner.id), ('move_type', '=', 'in_invoice' if resource == 'bill' else 'out_invoice'), ('state', '=', 'posted'), ('amount_residual', '>', 0)], 'name')
        if resource == 'bank':
            partner = company.partner_id if kind == 'invoices' else self._partner(company, partner_id, True)
            spec[resource] = ('res.partner.bank', [('partner_id', '=', partner.id)] + cdom, 'display_name')
        if resource not in spec:
            raise AccessError(_('Unsupported selection.'))
        model, domain, label = spec[resource]
        if model not in self.env:
            raise AccessError(_('This selection needs an optional integration.'))
        if resource in ('bill', 'invoice'):
            pass
        if resource == 'journal':
            if kind == 'invoices':
                domain += [('type', '=', 'sale')]
            elif kind in ('bills', 'refunds'):
                domain += [('type', '=', 'purchase')]
            elif kind == 'journals':
                domain += [('type', '=', 'general')]
        if resource == 'po' and partner_id:
            partner = self._partner(company, partner_id, True)
            domain += [('partner_id', '=', partner.id)]
        if query:
            search_fields = {'account': ['name', 'code'], 'product': ['name', 'default_code', 'barcode'], 'partner': ['name', 'ref', 'vat'], 'bank': ['acc_number']}.get(resource, ['name'])
            domain = expression.AND([domain, expression.OR([[(field, 'ilike', str(query)[:120])] for field in search_fields])])
        offset = max(0, min(int(offset or 0), 100000))
        limit = max(1, min(int(limit or 30), 81))
        records = self._env(company)[model].search(domain, limit=limit, offset=offset, order='id')
        result = []
        for r in records:
            data = {'id': r.id, 'name': r[label]}
            if resource in ('bill', 'invoice'):
                data['name'] = '%s · %.2f %s outstanding' % (r.name, r.amount_residual, r.currency_id.name)
            if resource == 'analytic':
                data.update(plan=r.plan_id.root_id.display_name, plan_id=r.plan_id.root_id.id)
            if resource == 'product':
                data.update(self._product_selection(r, company, kind))
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
        ids = {int(part) for distribution in distributions for key in distribution or {} for part in str(key).split(',') if part.isdigit() and int(part) > 0}
        accounts = self._env(company)['account.analytic.account'].search([('id', 'in', sorted(ids)), '|', ('company_id', '=', False), ('company_id', '=', company.id)])
        return {str(account.id): account.display_name for account in accounts}

    def _analytic_label_map(self, company, distributions):
        ids = {int(part) for distribution in distributions for key in distribution or {} for part in str(key).split(',') if part.isdigit() and int(part) > 0}
        accounts = self._env(company)['account.analytic.account'].search([('id', 'in', sorted(ids)), '|', ('company_id', '=', False), ('company_id', '=', company.id)])
        return {str(a.id): {'id': a.id, 'label': a.display_name, 'plan': a.plan_id.root_id.display_name, 'plan_id': a.plan_id.root_id.id} for a in accounts}

    def _move_values(self, company, kind, data):
        subtype = self._kind(kind)[2]
        journal = self._journal(company, data.get('journal_id'), ['general'] if subtype == 'entry' else ['sale'] if kind == 'invoices' else ['purchase'], kind=kind)
        partner = self._partner(company, data.get('partner_id'), subtype != 'entry')
        currency = self._relation(company, 'res.currency', data.get('currency_id') or company.currency_id.id, [('active', '=', True)], True)
        vals = {'move_type': subtype, 'journal_id': journal.id, 'company_id': company.id, 'currency_id': currency.id, 'ref': str(data.get('ref') or '').strip()[:250], 'payment_reference': str(data.get('payment_reference') or '')[:250], 'date': self._date(data.get('date')), 'partner_id': partner.id}
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
            line = {'account_id': account.id, 'name': name, 'analytic_distribution': self._analytic(company, row.get('analytic_distribution'))}
            if subtype == 'entry':
                debit, credit = (self._number(row.get('debit')), self._number(row.get('credit')))
                if debit < 0 or credit < 0 or (debit and credit) or (not (debit or credit)):
                    raise ValidationError(_('Each journal line needs either a positive debit or a positive credit.'))
                line.update(debit=debit, credit=credit, partner_id=self._partner(company, row.get('partner_id')).id, date_maturity=self._date(row.get('date_maturity'), False))
                tags = self._m2m(company, 'account.account.tag', row.get('tax_tag_ids', []), [('applicability', '=', 'taxes'), '|', ('country_id', '=', False), ('country_id', '=', company.account_fiscal_country_id.id)])
                line['tax_tag_ids'] = [Command.set(tags.ids)]
                taxes = self._m2m(company, 'account.tax', row.get('taxes_id', []), [('company_id', '=', company.id), ('type_tax_use', 'in', ['purchase', 'sale', 'none'])])
                line['tax_ids'] = [Command.set(taxes.ids)]
                if currency != company.currency_id:
                    line.update(currency_id=currency.id, amount_currency=self._number(row.get('amount_currency')))
            else:
                if account.account_type in ('asset_receivable', 'liability_payable'):
                    raise ValidationError(_('Use a suitable invoice-line account; Odoo creates receivable/payable lines.'))
                product = self._relation(company, 'product.product', row.get('product_id'), ['|', ('company_id', '=', False), ('company_id', '=', company.id)])
                taxes = self._m2m(company, 'account.tax', row.get('taxes_id', []), [('company_id', '=', company.id), ('type_tax_use', 'in', ['sale', 'none'] if kind == 'invoices' else ['purchase', 'none'])])
                discount = self._number(row.get('discount'))
                if not 0 <= discount <= 100:
                    raise ValidationError(_('Discount must be between 0 and 100.'))
                line.update(product_id=product.id, quantity=self._number(row.get('quantity'), True), price_unit=self._number(row.get('price_unit')), discount=discount, tax_ids=[Command.set(taxes.ids)])
                if row.get('product_uom_id'):
                    uom = self._relation(company, 'uom.uom', row['product_uom_id'], [('category_id', '=', product.uom_id.category_id.id)] if product else [], True)
                    line['product_uom_id'] = uom.id
                if kind == 'invoices' and row.get('purchase_line_id'):
                    raise ValidationError(_('Purchase lines cannot be linked to customer invoices.'))
                po_line = self._relation(company, 'purchase.order.line', row.get('purchase_line_id'), [('order_id.company_id', '=', company.id), ('order_id.partner_id', '=', partner.id), ('order_id.state', 'in', ['purchase', 'done'])])
                if po_line:
                    if product != po_line.product_id:
                        raise ValidationError(_('PO line product does not match the bill line.'))
                    line['purchase_line_id'] = po_line.id
            lines.append(Command.create(line))
        if subtype == 'entry':
            balance = sum((command[2]['debit'] - command[2]['credit'] for command in lines))
            if not company.currency_id.is_zero(balance):
                raise ValidationError(_('Journal entry is not balanced.'))
            vals['line_ids'] = lines
        else:
            vals.update(invoice_date=self._date(data.get('invoice_date')), invoice_line_ids=lines, invoice_payment_term_id=self._relation(company, 'account.payment.term', data.get('invoice_payment_term_id'), ['|', ('company_id', '=', False), ('company_id', '=', company.id)]).id, invoice_date_due=self._date(data.get('invoice_date_due'), False), narration=str(data.get('narration') or '')[:10000], payment_reference=str(data.get('payment_reference') or '')[:250], partner_bank_id=self._relation(company, 'res.partner.bank', data.get('partner_bank_id'), [('partner_id', '=', company.partner_id.id if kind == 'invoices' else partner.id), '|', ('company_id', '=', False), ('company_id', '=', company.id)]).id)
        return vals

    def _save(self, company, kind, data):
        user, roles = self._actor('preparer', kind=kind)
        model = self._kind(kind)[0]
        if kind != 'invoices' and (not company.pbw_accounting_journal_ids):
            raise AccessError(_('Configure the company portal accounting journals first.'))
        vals = self._move_values(company, kind, data)
        record = self._record(company, kind, data['id']) if data.get('id') else False
        if record:
            record._pbw_accounting_lock(data.get('version'))
            if record.state != 'draft' or record.pbw_accounting_review in ('submitted', 'approved'):
                raise UserError(_('Only an editable draft or returned document can be saved.'))
            if record.pbw_accounting_issuer_id and record.pbw_accounting_issuer_id != user and (not (roles['direct'] and (not record.pbw_accounting_review_required))):
                raise AccessError(_('This restricted draft belongs to another preparer.'))
            line_key = 'line_ids' if kind == 'journals' else 'invoice_line_ids'
            if kind == 'invoices':
                existing = set(record.invoice_line_ids.ids)
                seen = set()
                commands = []
                for row, command in zip(data.get('lines', []), vals[line_key]):
                    line_id = self._id(row['id']) if row.get('id') else False
                    if line_id:
                        if line_id not in existing or line_id in seen:
                            raise AccessError(_('An invoice line is not available in this invoice.'))
                        seen.add(line_id)
                        commands.append(Command.update(line_id, command[2]))
                    else:
                        commands.append(command)
                vals[line_key] = commands + [Command.delete(line_id) for line_id in sorted(existing - seen)]
            else:
                vals[line_key] = [Command.clear()] + vals[line_key]
            record.write(dict(vals, pbw_accounting_review_required=record.pbw_accounting_review_required or roles['restricted'], pbw_accounting_review='draft', pbw_accounting_reviewer_id=False, pbw_accounting_issuer_id=user.id))
        else:
            record = self._env(company)[model].create(dict(vals, pbw_accounting_issuer_id=user.id, pbw_accounting_review_required=roles['restricted']))
        self._audit(record, 'Saved draft', ', '.join(sorted(vals)))
        if data.get('post'):
            if not roles['direct']:
                raise AccessError(_('Direct posting is not available to this user.'))
            self._act(company, kind, record.id, 'post', dict(data, version=str(record.write_date)))
        elif data.get('submit'):
            self._act(company, kind, record.id, 'submit', {'version': str(record.write_date)})
        return self._detail(company, kind, record.id)

    def _act(self, company, kind, record_id, action, data):
        user, roles = self._actor(kind=kind)
        record = self._record(company, kind, record_id)
        record._pbw_accounting_lock(data.get('version'))
        comment = str(data.get('comment') or '')[:2000]
        if action == 'process-edi':
            if kind != 'invoices' or not (roles['direct'] or roles['approver']) or record.state != 'posted':
                raise AccessError(_('Posting permission and a posted customer invoice are required.'))
            if company.country_id.code != 'SA' or 'edi_document_ids' not in record._fields or (not record.edi_document_ids):
                raise UserError(_('No Saudi e-invoicing document is configured for this invoice.'))
            if any((document.state == 'to_cancel' for document in record.edi_document_ids)):
                raise UserError(_('An E-Invoicing cancellation is pending. Handle it internally before processing from this workspace.'))
            method = getattr(record, 'action_process_edi_web_services', None)
            if not callable(method):
                raise UserError(_('This Odoo installation does not expose the native Process E-Invoicing action.'))
            method(with_commit=False)
            return self._detail(company, kind, record.id)
        if action == 'submit':
            self._actor('preparer', kind=kind)
            if not record.pbw_accounting_review_required or record.state != 'draft' or record.pbw_accounting_review not in ('draft', 'returned'):
                raise UserError(_('Only restricted editable drafts can be submitted.'))
            if record.pbw_accounting_issuer_id != user:
                raise AccessError(_('Only the preparer can submit this document.'))
            record.write({'pbw_accounting_review': 'submitted', 'pbw_accounting_comment': False})
        elif action in ('return', 'post'):
            if record.pbw_accounting_review_required:
                self._actor('approver', kind=kind)
                if record.state != 'draft' or record.pbw_accounting_review != 'submitted':
                    raise UserError(_('Only submitted drafts can be reviewed.'))
                if record.pbw_accounting_issuer_id == user:
                    raise AccessError(_('Another accounting approver must review your document.'))
                if action == 'post':
                    record._pbw_accounting_validate_submission()
            elif action != 'post' or not roles['direct'] or record.state != 'draft':
                raise AccessError(_('Direct posting is not permitted.'))
            if action == 'return':
                if not comment:
                    raise ValidationError(_('Enter a reason for returning the document.'))
                record.write({'pbw_accounting_review': 'returned', 'pbw_accounting_comment': comment, 'pbw_accounting_reviewer_id': user.id})
            else:
                warnings = '\n'.join(filter(None, [record.abnormal_amount_warning, record.abnormal_date_warning]))
                if warnings and data.get('confirm_abnormal') is not True:
                    raise UserError(_('ACCOUNTING WARNING: %s. Review and acknowledge this warning before posting.') % warnings)
                if kind in ('bills', 'refunds') and record.ref:
                    self.env.cr.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ['pbw-bill:%s:%s:%s:%s' % (company.id, record.partner_id.id, record.move_type, record.ref.strip().lower())])
                    self.env.cr.execute("SELECT id FROM account_move\n                        WHERE company_id=%s AND partner_id=%s AND move_type=%s\n                        AND lower(btrim(ref))=lower(btrim(%s)) AND id!=%s AND state!='cancel' LIMIT 1", [company.id, record.partner_id.id, record.move_type, record.ref, record.id])
                    found = self.env.cr.fetchone()
                    duplicate = self._env(company)['account.move'].browse(found[0] if found else [])
                    if duplicate:
                        raise UserError(_('A bill/credit note with this vendor reference already exists: %s') % duplicate.display_name)
                record.write({'pbw_accounting_review': 'approved' if record.pbw_accounting_review_required else 'draft', 'pbw_accounting_reviewer_id': user.id if record.pbw_accounting_review_required else False, 'pbw_accounting_comment': comment})
                result = record.with_context(_pbw_accounting_token=_REVIEW_TOKEN, validate_analytic=True).action_post()
                if isinstance(result, dict) and result.get('res_model') == 'account.autopost.bills.wizard' and record.state == 'posted':
                    pass
                elif isinstance(result, dict) and result.get('type') == 'ir.actions.act_window':
                    raise UserError(_('An additional accounting wizard is required. Complete this operation internally.'))
                if record.state != 'posted':
                    raise UserError(_('The accounting method did not post this document.'))
        elif action in ('reconcile', 'unreconcile'):
            if not (roles['approver'] or roles['direct']):
                raise AccessError(_('Accounting posting permission is required.'))
            raise AccessError(_('This action is not available in the native invoice workspace.'))
            method = 'action_reconcile_invoices' if action == 'reconcile' else 'action_unreconcile_invoices'
            getattr(record, method)()
        elif action in ('reset', 'request-reset'):
            if not (roles['preparer'] or roles['approver']):
                raise AccessError(_('Accounting access is required.'))
            if record.state not in ('posted', 'cancel') or not comment:
                raise UserError(_('Enter a reason for requesting a reset.'))
            if record.pbw_accounting_reset_pending:
                raise UserError(_('A reset request is already pending.'))
            models.Model.write(record, {'pbw_accounting_reset_pending': True, 'pbw_accounting_reset_requested_by': user.id, 'pbw_accounting_reset_reason': comment})
            managers = self._env(company)['res.users'].search([('active', '=', True), ('share', '=', False), ('company_ids', 'in', company.id), ('groups_id', 'in', self.env.ref('account.group_account_manager').id)])
            for manager in managers:
                record.activity_schedule('mail.mail_activity_data_todo', user_id=manager.id, summary=_('Reset to Draft permission requested'), note=comment)
            action = 'Requested Reset to Draft (document remains posted/cancelled)'
        elif action == 'cancel':
            self._actor('preparer', kind=kind)
            if record.state != 'draft' or record.pbw_accounting_review not in ('draft', 'returned') or (record.pbw_accounting_issuer_id != user and (not (roles['direct'] and (not record.pbw_accounting_review_required)))):
                raise AccessError(_('Only an authorized preparer can cancel this draft.'))
            getattr(record, 'button_cancel')()
        elif action == 'find':
            self._actor('preparer', kind=kind)
            raise AccessError(_('Unsupported operation.'))
            if record.pbw_accounting_issuer_id != user and (not (roles['direct'] and (not record.pbw_accounting_review_required))):
                raise AccessError(_('Only the preparer may change selected documents.'))
            getattr(record, 'action_find_matching_invoices')()
        else:
            raise AccessError(_('Unsupported accounting action.'))
        if action in ('return', 'post') and record.pbw_accounting_review_required:
            record._pbw_accounting_notify(record.pbw_accounting_issuer_id, _('Accounting document %s: %s') % (record.display_name, _('Posted') if action == 'post' else _('Returned for correction')), _('%(user)s: %(comment)s', user=user.name, comment=comment or _('Review completed.')))
        self._audit(record, action, comment)
        return self._detail(company, kind, record.id)

    def _audit(self, record, action, detail=''):
        user = self.env.user
        record.message_post(body=_('Accounting: %(action)s by %(user)s. %(detail)s', action=action, user=user.name, detail=detail), message_type='comment', subtype_xmlid='mail.mt_note', author_id=user.partner_id.id, email_from=user.email_formatted or record.company_id.partner_id.email_formatted or 'Accounting <noreply@localhost>')

    def _detail(self, company, kind, record_id=None):
        user, roles = self._actor(kind=kind)
        model, title, subtype = self._kind(kind)
        record = self._record(company, kind, record_id) if record_id else False
        default_tax = company.account_sale_tax_id if kind == 'invoices' else company.account_purchase_tax_id if kind in ('bills', 'refunds') else self.env['account.tax']
        data = {'id': record.id if record else 0, 'company_id': company.id, 'kind': kind, 'default_taxes': [{'id': tax.id, 'name': tax.name} for tax in default_tax], 'company_currency_name': company.currency_id.name, 'analytic_names': {}, 'analytic_labels': {}, 'currency_id': company.currency_id.id, 'currency_name': company.currency_id.name, 'date': fields.Date.context_today(self).isoformat(), 'invoice_date': fields.Date.context_today(self).isoformat(), 'lines': [], 'bill_ids': [], 'invoice_ids': [], 'purchase_order_ids': [], 'allocations': [], 'destinations': [], 'selections': {}, 'roles': roles, 'state': 'draft', 'review': 'draft', 'name': 'New', 'version': '', 'editable': roles['preparer'], 'can_review': False, 'can_post': roles['direct'], 'review_required': roles['restricted'], 'is_ceo': False, 'attachments': []}
        if not record:
            if roles['preparer']:
                defaults = self._defaults(company, kind)
                data.update(defaults)
            return data
        data.update(self._row(record, kind), version=str(record.write_date), review=record.pbw_accounting_review if record.pbw_accounting_review_required else 'not_required', review_required=record.pbw_accounting_review_required, comment=record.pbw_accounting_comment or '', issuer_id=record.pbw_accounting_issuer_id.id)
        data['editable'] = roles['preparer'] and (not record.pbw_accounting_issuer_id or record.pbw_accounting_issuer_id == user or (roles['direct'] and (not record.pbw_accounting_review_required))) and (record.state == 'draft' and record.pbw_accounting_review in ('draft', 'returned'))
        data['can_post'] = roles['direct'] and data['editable'] and (not record.pbw_accounting_review_required)
        data['can_review'] = record.pbw_accounting_review_required and roles['approver'] and (record.pbw_accounting_issuer_id != user) and (record.state == 'draft' and record.pbw_accounting_review == 'submitted')
        scalar_fields = ['ref', 'payment_reference', 'invoice_date', 'invoice_date_due', 'narration', 'description', 'payment_method', 'receipt_method', 'amount', 'forecast_amount', 'transaction_type', 'priority', 'funding_status', 'analytic_distribution', 'has_bank_fees', 'fee_amount', 'fee_analytic_distribution', 'approved_amount', 'actual_amount', 'ceo_comment', 'planned_date', 'allocated_amount', 'remaining_to_reconcile']
        scalar_fields += ['reset_request_pending', 'pbw_accounting_reset_pending']
        for name in scalar_fields:
            if name in record._fields:
                value = record[name]
                data[name] = str(value) if isinstance(value, date) else value
        for name in ('partner_id', 'journal_id', 'account_id', 'currency_id', 'invoice_payment_term_id', 'project_id', 'category_id', 'run_id', 'fee_account_id', 'fee_tax_id', 'partner_bank_id'):
            if name in record._fields:
                value = record[name]
                data[name] = value.id
                data['selections'][name] = {'id': value.id, 'name': value.display_name or ''}
        if kind == 'invoices':
            data['edi_state'] = record.edi_state if 'edi_state' in record._fields else ''
            data['edi_error'] = html2plaintext(record.edi_error_message or '') if 'edi_error_message' in record._fields else ''
            data['can_process_edi'] = bool(record.state == 'posted' and (roles['direct'] or roles['approver']) and (company.country_id.code == 'SA') and ('edi_document_ids' in record._fields) and any((document.state == 'to_send' for document in record.edi_document_ids)) and (not any((document.state == 'to_cancel' for document in record.edi_document_ids))) and callable(getattr(record, 'action_process_edi_web_services', None)))
        data['currency_name'] = record.currency_id.name
        for name in ('bill_ids', 'invoice_ids', 'purchase_order_ids'):
            if name in record._fields:
                data[name] = record[name].ids
                data['selections'][name] = [{'id': r.id, 'name': r.display_name} for r in record[name]]
        distributions = record.line_ids.mapped('analytic_distribution')
        data['analytic_labels'] = self._analytic_label_map(company, distributions)
        data['analytic_names'] = {key: value['label'] for key, value in data['analytic_labels'].items()}
        data['warnings'] = '\n'.join(filter(None, [record.abnormal_amount_warning, record.abnormal_date_warning]))
        lines = record.line_ids if kind == 'journals' else record.invoice_line_ids
        for line in lines:
            row = {'id': line.id, 'name': line.name or '', 'account_id': line.account_id.id, 'account_name': line.account_id.display_name or '', 'product_id': line.product_id.id, 'product_name': line.product_id.display_name or '', 'product_uom_id': line.product_uom_id.id, 'uom_name': line.product_uom_id.display_name or '', 'partner_id': line.partner_id.id, 'partner_name': line.partner_id.display_name or '', 'quantity': line.quantity, 'price_unit': line.price_unit, 'discount': line.discount, 'debit': line.debit, 'credit': line.credit, 'amount_currency': line.amount_currency, 'display_type': line.display_type, 'date_maturity': str(line.date_maturity or ''), 'analytic_distribution': line.analytic_distribution or {}, 'taxes_id': line.tax_ids.ids, 'tax_names': [{'id': t.id, 'name': t.name} for t in line.tax_ids], 'tax_tag_ids': line.tax_tag_ids.ids, 'grid_names': [{'id': t.id, 'name': t.display_name} for t in line.tax_tag_ids], 'purchase_line_id': line.purchase_line_id.id, 'subtotal': line.price_subtotal}
            data['lines'].append(row)
        data.update(untaxed=record.amount_untaxed, tax=record.amount_tax, total=record.amount_total, balance_due=record.amount_residual, journal_items=[{'account': l.account_id.display_name, 'partner': l.partner_id.display_name, 'name': l.name or '', 'debit': l.debit, 'credit': l.credit, 'analytic_distribution': l.analytic_distribution or {}, 'tax_names': [{'id': t.id, 'name': t.name} for t in l.tax_ids], 'grid_names': [{'id': t.id, 'name': t.display_name} for t in l.tax_tag_ids]} for l in record.line_ids])
        attachments = self._env(company)['ir.attachment'].search([('res_model', '=', model), ('res_id', '=', record.id), ('type', '=', 'binary')], limit=100)
        data['attachments'] = [{'id': a.id, 'name': a.name} for a in attachments]
        data['history'] = [{'date': str(m.date), 'author': m.author_id.name or '', 'body': html2plaintext(m.body)} for m in record.message_ids.sorted('id', reverse=True)[:100]]
        return data

    def _create_bill_from_po(self, company, po_id, version):
        user, roles = self._actor('preparer')
        if not user.has_group('portal_backend_workspace.purchase__group_portal_purchase_user'):
            raise AccessError(_('The Purchase User working role is required to create vendor bills from orders.'))
        po = self._relation(company, 'purchase.order', po_id, [('company_id', '=', company.id), ('state', 'in', ['purchase', 'done'])], True)
        po._pbw_purchase_lock()
        if str(po.write_date) != version:
            raise UserError(_('This purchase order changed. Reload it before creating a bill.'))
        defaults = self._defaults(company, 'bills', po.partner_id.id)
        journal = self._journal(company, defaults['journal_id'], ['purchase'])
        before = po.invoice_ids
        po.with_context(default_journal_id=journal.id, allowed_company_ids=[company.id]).action_create_invoice()
        po.invalidate_recordset()
        created = po.invoice_ids - before
        if len(created) != 1 or created.move_type != 'in_invoice':
            raise UserError(_('Expected one native draft vendor bill. No bill was created.'))
        self._journal(company, created.journal_id.id, ['purchase'])
        created.write({'pbw_accounting_issuer_id': user.id, 'pbw_accounting_review_required': roles['restricted']})
        self._audit(created, 'Created draft vendor bill from purchase order', po.name)
        return {'url': '/my/workspace/accounting/bills/%s?company_id=%s' % (created.id, company.id)}

    def _po_lines(self, company, po_id):
        self._actor('preparer')
        self._kind('bills')
        po = self._relation(company, 'purchase.order', po_id, [('company_id', '=', company.id), ('state', 'in', ['purchase', 'done'])], True)
        data = {'analytic_labels': self._analytic_label_map(company, po.order_line.mapped('analytic_distribution')), 'analytic_names': self._analytic_name_map(company, po.order_line.mapped('analytic_distribution')), 'partner_id': po.partner_id.id, 'partner_name': po.partner_id.display_name, 'currency_id': po.currency_id.id, 'currency_name': po.currency_id.name, 'ref': po.partner_ref or '', 'lines': []}
        for line in po.order_line:
            if line.display_type:
                data['lines'].append({'display_type': line.display_type, 'name': line.name})
            elif line.qty_to_invoice > 0:
                native = line._prepare_account_move_line()
                account = line.product_id.product_tmpl_id.get_product_accounts(fiscal_pos=po.fiscal_position_id).get('expense')
                data['lines'].append({'name': native.get('name') or line.name, 'product_id': line.product_id.id, 'product_name': line.product_id.display_name, 'quantity': native.get('quantity', line.qty_to_invoice), 'product_uom_id': line.product_uom.id, 'uom_name': line.product_uom.display_name, 'price_unit': native.get('price_unit', line.price_unit), 'discount': native.get('discount', line.discount), 'purchase_line_id': line.id, 'account_id': account.id if account else False, 'account_name': account.display_name if account else '', 'taxes_id': line.taxes_id.ids, 'tax_names': [{'id': t.id, 'name': t.name} for t in line.taxes_id], 'analytic_distribution': line.analytic_distribution or {}})
        if not any((not r.get('display_type') for r in data['lines'])):
            raise UserError(_('This PO has no quantity ready to bill. Check its bill control policy and receipts.'))
        return data

    def _preview(self, company, kind, data):
        self._actor('preparer', kind=kind)
        data = dict(data)
        defaults = self._defaults(company, kind, data.get('partner_id'))
        for key in ('journal_id', 'currency_id'):
            if not data.get(key):
                data[key] = defaults[key]
        if not data.get('journal_id'):
            raise ValidationError(_('Select an available journal of the correct type in Accounting Settings.'))
        vals = self._move_values(company, kind, data)

        class PreviewRollback(Exception):
            pass
        result = None
        try:
            with self.env.cr.savepoint():
                record = self._env(company)['account.move'].with_context(tracking_disable=True, mail_create_nolog=True, mail_create_nosubscribe=True).create(vals)
                result = {'untaxed': record.amount_untaxed, 'tax': record.amount_tax, 'total': record.amount_total, 'currency': record.currency_id.name, 'line_amounts': record.invoice_line_ids.mapped('price_subtotal') if kind != 'journals' else [], 'journal_items': [{'account': l.account_id.display_name, 'partner': l.partner_id.display_name, 'name': l.name or '', 'debit': l.debit, 'credit': l.credit, 'analytic_distribution': l.analytic_distribution or {}, 'tax_names': [{'id': t.id, 'name': t.name} for t in l.tax_ids], 'grid_names': [{'id': t.id, 'name': t.display_name} for t in l.tax_tag_ids]} for l in record.line_ids]}
                raise PreviewRollback()
        except PreviewRollback:
            pass
        return result
