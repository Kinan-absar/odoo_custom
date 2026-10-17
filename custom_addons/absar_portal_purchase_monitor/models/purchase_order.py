from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    absar_portal_project_id = fields.Many2one('project.project', string='Portal Project', check_company=True)
    absar_portal_preparer_id = fields.Many2one('res.users', string='Portal Prepared By', readonly=True, copy=False)
    absar_portal_review_state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Awaiting Approval'),
        ('approved', 'Approved'), ('returned', 'Returned for Correction')],
        default='draft', string='Portal Review Status', copy=False, tracking=True)
    absar_portal_review_note = fields.Text('Review Note', copy=False)

    def action_absar_portal_approve(self):
        if not self.env.user.has_group('absar_portal_purchase_monitor.group_portal_purchase_approver'):
            raise UserError(_('Purchase approval permission is required.'))
        for po in self:
            if po.company_id not in self.env.user.company_ids:
                raise UserError(_('You cannot review purchase orders in another company.'))
            if po.absar_portal_review_state != 'submitted' or po.state not in ('draft', 'sent'):
                raise UserError(_('Only submitted RFQs can be approved.'))
            if po.absar_portal_preparer_id == self.env.user:
                raise UserError(_('You cannot approve your own purchase request.'))
            # Use native confirmation flow; company purchase policies and custom
            # signing automation remain responsible for any subsequent approvals.
            po.sudo().with_company(po.company_id).button_confirm()
            po.sudo().absar_portal_review_state = 'approved'
            if po.absar_portal_preparer_id.partner_id:
                po.sudo().message_subscribe(partner_ids=po.absar_portal_preparer_id.partner_id.ids)
            po.sudo().message_post(body=_('Portal purchase submission approved by %s.') % self.env.user.name)

    def action_absar_portal_return(self):
        if not self.env.user.has_group('absar_portal_purchase_monitor.group_portal_purchase_approver'):
            raise UserError(_('Purchase approval permission is required.'))
        for po in self:
            if po.company_id not in self.env.user.company_ids:
                raise UserError(_('You cannot review purchase orders in another company.'))
            if po.absar_portal_review_state != 'submitted':
                raise UserError(_('Only submitted RFQs can be returned.'))
            po.sudo().absar_portal_review_state = 'returned'
            if po.absar_portal_preparer_id.partner_id:
                po.sudo().message_subscribe(partner_ids=po.absar_portal_preparer_id.partner_id.ids)
            po.sudo().message_post(body=_('Returned to preparer for correction.'))


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    absar_expense_account_id = fields.Many2one('account.account', string='Expense Account', check_company=False)

    def _prepare_account_move_line(self, move=False):
        vals = super()._prepare_account_move_line(move=move)
        if self.absar_expense_account_id:
            vals['account_id'] = self.absar_expense_account_id.id
        return vals
