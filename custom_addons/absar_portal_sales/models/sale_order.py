from odoo import fields, models

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    absar_portal_creator_id = fields.Many2one('res.users', string='Portal Prepared By', readonly=True, index=True, copy=False)
    absar_portal_review_state = fields.Selection([
        ('draft', 'Portal Draft'), ('submitted', 'Awaiting Internal Approval'),
        ('approved', 'Approved for Sending'), ('returned', 'Returned for Correction')],
        string='Portal Review', default='draft', copy=False, tracking=True, index=True)
    absar_portal_review_note = fields.Text(string='Review Notes', copy=False)
    absar_portal_approver_id = fields.Many2one('res.users', string='Portal Approved By', readonly=True, copy=False)
