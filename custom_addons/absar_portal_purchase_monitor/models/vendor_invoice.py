from odoo import api,fields,models
from odoo.exceptions import ValidationError
class VendorInvoiceCompany(models.Model):
    _inherit='portal.vendor.invoice'
    # No default/backfill: historical records without a PO must be classified
    # explicitly, rather than assigned silently to an arbitrary company.
    company_id=fields.Many2one('res.company',string='Company',index=True)

    @api.model
    def create(self,vals):
        vals=dict(vals);po=self.env['purchase.order'].sudo().browse(vals.get('po_id')).exists() if vals.get('po_id') else False
        company=po.company_id if po else self.env.company
        if self.env.user.share or not vals.get('company_id'):vals['company_id']=company.id
        if vals['company_id'] not in self.env.user.company_ids.ids:raise ValidationError('Company is not permitted.')
        if po and (po.company_id.id!=vals['company_id'] or po.partner_id.id!=vals.get('partner_id')):raise ValidationError('The purchase order must match the vendor and company.')
        return super().create(vals)
