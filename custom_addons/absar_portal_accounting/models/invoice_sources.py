from odoo import models, _
from odoo.exceptions import AccessError,UserError

class CustomerInvoiceSources(models.AbstractModel):
    _inherit='absar.portal.accounting.service'

    def _source_domain(self,company,kind):
        self._kind('invoices')
        if kind=='sales-orders':return 'sale.order',[('company_id','=',company.id),('state','in',['sale','done'])]
        if kind=='ipcs':return 'construction.ipc',[('company_id','=',company.id),('contract_direction','=','inbound'),('state','in',['approved','done'])]
        raise AccessError(_('Unsupported invoice source.'))

    def _source_invoice(self,company,kind,ident,version):
        user,roles=self._actor('preparer',kind='invoices');model,domain=self._source_domain(company,kind)
        source=self._relation(company,model,ident,domain,True)
        source.flush_recordset(['write_date'])
        self.env.cr.execute('SELECT id FROM '+source._table+' WHERE id=%s FOR UPDATE',[source.id])
        source.invalidate_recordset()
        if not version or version!=str(source.write_date):raise UserError(_('This source changed. Reopen it before invoicing.'))
        if source.company_id!=company or source.state not in (['sale','done'] if kind=='sales-orders' else ['approved','done']):raise UserError(_('The source is no longer eligible for invoicing.'))
        defaults=self._defaults(company,'invoices');journal=self._journal(company,defaults['journal_id'],['sale'])
        if kind=='sales-orders':
            # Native sale_line_ids and invoiceable/delivered quantities are retained.
            moves=source.with_context(default_journal_id=journal.id)._create_invoices()
            if len(moves)!=1:raise UserError(_('The source must produce exactly one customer invoice.'))
            move=moves
        else:
            if source.contract_direction!='inbound':raise AccessError(_('Only customer IPCs can be invoiced here.'))
            contract=source.contract_id
            self._journal(company,contract.journal_id.id,['sale'])
            if contract.company_id!=company or (contract.partner_id.company_id and contract.partner_id.company_id!=company):raise AccessError(_('Contract company mismatch.'))
            for account in (contract.work_account_id|contract.advance_account_id|contract.retention_account_id):self._account(company,account.id)
            if contract.tax_id.company_id!=company or contract.tax_id.type_tax_use not in ('sale','none'):raise UserError(_('Configure a sales tax in this company on the contract.'))
            source.action_create_move();move=source.move_id
        if not move or move.company_id!=company or move.move_type!='out_invoice' or move.state!='draft':raise UserError(_('The native source did not create a draft customer invoice in this company.'))
        self._journal(company,move.journal_id.id,['sale'])
        move.write(dict(portal_accounting_issuer_id=user.id,portal_accounting_review_required=roles['restricted']))
        self._audit(move,'Created customer invoice from '+kind,source.display_name)
        return move
