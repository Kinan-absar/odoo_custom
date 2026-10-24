"""Approved No-PO MR -> editable vendor-bill draft, using the existing gateway."""
from odoo import models, _
from odoo.exceptions import AccessError, UserError


class AccountingRequestSource(models.AbstractModel):
    _inherit = 'absar.portal.accounting.service'

    def _mr_source(self, company, ident, lock=False):
        user, roles = self._actor('preparer')
        if not any(user.has_group('employee_portal_suite.group_employee_portal_' + role)
                   for role in ('admin', 'superadmin')):
            raise AccessError(_('Only a portal administrator can start a bill from MR Control.'))
        ident = self._id(ident)
        rec = self._env(company)['material.request'].search([
            ('id', '=', ident), '|', ('project_id.company_id', '=', company.id), '&',
            ('project_id.company_id', '=', False), ('employee_id.company_id', '=', company.id)], limit=1)
        if not rec:
            raise AccessError(_('Material Request is not available in this company.'))
        if lock:
            self.env.cr.execute('SELECT id FROM material_request WHERE id=%s FOR UPDATE', [rec.id])
            rec.invalidate_recordset()
        if (rec.project_id.company_id or rec.employee_id.company_id) != company:
            raise AccessError(_('Material Request is not available in this company.'))
        if rec.state != 'approved' or not rec.no_po_required or rec.purchase_order_ids:
            raise UserError(_('Use an approved No PO Required MR with no linked PO. For PO-based requests, create the bill from the PO.'))
        return rec

    def _mr_bill_draft(self, company, ident, data):
        rec = self._mr_source(company, ident)
        if not 1 <= len(rec.line_ids) <= 200:
            raise UserError(_('The MR must have between 1 and 200 materials to prepare a vendor bill.'))
        taxes = company.account_purchase_tax_id
        account = self._account(company, rec.expense_account_id.id, False) if rec.expense_account_id else rec.expense_account_id
        data.update(material_request_id=rec.id, material_request_name=rec.name,
                    invoice_origin=rec.name, lines=[])
        for material in rec.line_ids:
            data['lines'].append(dict(id=0, name=material.item_name or rec.name,
                quantity=material.qty_required or 1, price_unit=0, discount=0, product_id=0,
                product_uom_id=material.uom_id.id or 0, uom_name=material.uom_id.display_name or '',
                account_id=account.id or 0, account_name=account.display_name or '',
                analytic_distribution={}, taxes_id=taxes.ids,
                tax_names=[{'id':tax.id,'name':tax.name} for tax in taxes], tax_tag_ids=[], grid_names=[]))
        return data

    def _save(self, company, kind, data):
        if data.get('material_request_id'):
            if kind != 'bills':
                raise UserError(_('MR sources are only available for vendor bills.'))
            if data.get('id'):
                record = self._record(company, kind, data['id'])
                if record.material_request_id.id != self._id(data['material_request_id']):
                    raise AccessError(_('The Material Request link cannot be changed.'))
            else:
                # Recheck on Save, not only when opening the form. Serialize with
                # MR approval/follow-up changes so a stale page cannot bypass routing.
                self._mr_source(company, data['material_request_id'], lock=True)
        return super()._save(company, kind, data)

    def _move_values(self, company, kind, data):
        vals = super()._move_values(company, kind, data)
        if kind == 'bills' and data.get('material_request_id') and not data.get('id'):
            rec = self._mr_source(company, data['material_request_id'])
            vals.update(material_request_id=rec.id, invoice_origin=rec.name)
        return vals

    def _detail(self, company, kind, record_id=None):
        data = super()._detail(company, kind, record_id)
        if kind == 'bills' and record_id:
            rec = self._record(company, kind, record_id)
            if rec.material_request_id:
                data.update(material_request_id=rec.material_request_id.id,
                            material_request_name=rec.material_request_id.name)
        return data
