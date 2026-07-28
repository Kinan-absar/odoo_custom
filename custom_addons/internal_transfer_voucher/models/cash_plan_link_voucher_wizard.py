from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CashPlanLinkVoucherWizard(models.TransientModel):
    _name = 'cash.plan.link.voucher.wizard'
    _description = 'Link Existing Voucher to Planned Cash Movement'

    line_id = fields.Many2one(
        'cash.plan.line',
        string='Planned Cash Movement',
        required=True,
        readonly=True,
    )
    flow_type = fields.Selection(related='line_id.flow_type', readonly=True)
    company_id = fields.Many2one(related='line_id.company_id', readonly=True)
    partner_id = fields.Many2one(related='line_id.partner_id', readonly=True)

    payment_voucher_id = fields.Many2one(
        'account.payment.voucher',
        string='Existing Payment Voucher',
        domain="[('company_id', '=', company_id), ('state', '!=', 'cancel')]",
    )
    receipt_voucher_id = fields.Many2one(
        'account.receipt.voucher',
        string='Existing Receipt Voucher',
        domain="[('company_id', '=', company_id), ('state', '!=', 'cancel')]",
    )

    @api.onchange('line_id')
    def _onchange_line_id(self):
        self.payment_voucher_id = False
        self.receipt_voucher_id = False

    @api.constrains('payment_voucher_id', 'receipt_voucher_id', 'flow_type')
    def _check_selected_voucher_type(self):
        for wizard in self:
            if wizard.flow_type == 'out' and not wizard.payment_voucher_id:
                raise ValidationError(_('Select an existing Payment Voucher.'))
            if wizard.flow_type == 'in' and not wizard.receipt_voucher_id:
                raise ValidationError(_('Select an existing Receipt Voucher.'))

    def _detach_auto_unplanned_line(self, voucher, voucher_field):
        old_line = voucher.cash_plan_line_id
        if not old_line:
            old_line = self.env['cash.plan.line'].sudo().search([
                (voucher_field, '=', voucher.id),
            ], limit=1)
        if not old_line or old_line == self.line_id:
            return
        if not old_line.is_unplanned:
            raise UserError(_(
                'Voucher %(voucher)s is already linked to planned movement %(line)s. '
                'Unlink it there before linking it to another planned movement.',
                voucher=voucher.display_name,
                line=old_line.display_name,
            ))
        # Remove the automatically-created unplanned line so actuals are not counted twice.
        voucher.with_context(skip_cash_plan_link_lock=True).write({'cash_plan_line_id': False})
        old_line.sudo().unlink()

    def action_link_voucher(self):
        self.ensure_one()
        line = self.line_id
        if line.state == 'cancel':
            raise UserError(_('A cancelled planned movement cannot be linked to a voucher.'))
        if line.flow_type == 'out':
            if line.payment_voucher_id and line.payment_voucher_id != self.payment_voucher_id:
                raise UserError(_('This planned payment is already linked to another Payment Voucher.'))
            if line.receipt_voucher_id:
                raise UserError(_('A payment plan cannot be linked to a Receipt Voucher.'))
            voucher = self.payment_voucher_id
            if not voucher:
                raise UserError(_('Select an existing Payment Voucher.'))
            if voucher.company_id != line.company_id:
                raise UserError(_('The Payment Voucher and planned payment must belong to the same company.'))
            if voucher.currency_id != line.currency_id:
                raise UserError(_('The Payment Voucher and planned payment must use the same currency.'))
            if line.partner_id and voucher.partner_id.commercial_partner_id != line.partner_id.commercial_partner_id:
                raise UserError(_('The Payment Voucher must belong to the same vendor as the planned payment.'))
            self._detach_auto_unplanned_line(voucher, 'payment_voucher_id')
            line.write({
                'payment_voucher_id': voucher.id,
                'state': 'executed' if voucher.state == 'posted' else line.state,
            })
            voucher.with_context(skip_cash_plan_link_lock=True).write({'cash_plan_line_id': line.id})
        else:
            if line.receipt_voucher_id and line.receipt_voucher_id != self.receipt_voucher_id:
                raise UserError(_('This planned receipt is already linked to another Receipt Voucher.'))
            if line.payment_voucher_id:
                raise UserError(_('A receipt plan cannot be linked to a Payment Voucher.'))
            voucher = self.receipt_voucher_id
            if not voucher:
                raise UserError(_('Select an existing Receipt Voucher.'))
            if voucher.company_id != line.company_id:
                raise UserError(_('The Receipt Voucher and planned receipt must belong to the same company.'))
            if voucher.currency_id != line.currency_id:
                raise UserError(_('The Receipt Voucher and planned receipt must use the same currency.'))
            if line.partner_id and voucher.partner_id.commercial_partner_id != line.partner_id.commercial_partner_id:
                raise UserError(_('The Receipt Voucher must belong to the same customer as the planned receipt.'))
            self._detach_auto_unplanned_line(voucher, 'receipt_voucher_id')
            line.write({
                'receipt_voucher_id': voucher.id,
                'state': 'executed' if voucher.state == 'posted' else line.state,
            })
            voucher.with_context(skip_cash_plan_link_lock=True).write({'cash_plan_line_id': line.id})

        return {'type': 'ir.actions.act_window_close'}
