from odoo import models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_open_voucher_payment(self):
        """Open the custom voucher for a posted customer invoice/vendor bill."""
        self.ensure_one()

        if self.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError(_("This action is only available for customer invoices and vendor bills."))
        if self.state != 'posted':
            raise UserError(_("The invoice/bill must be posted before creating a voucher."))
        if self.payment_state not in ('not_paid', 'partial') or self.amount_residual <= 0:
            raise UserError(_("There is no outstanding amount to pay on this invoice/bill."))

        company = self.company_id
        partner = self.commercial_partner_id or self.partner_id
        amount = abs(self.amount_residual)

        if self.move_type == 'in_invoice':
            counterpart = self.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
            )[:1]
            if not counterpart:
                raise UserError(_("No open payable account line was found on this vendor bill."))

            return {
                'type': 'ir.actions.act_window',
                'name': _('Payment Voucher'),
                'res_model': 'account.payment.voucher',
                'view_mode': 'form',
                'view_id': self.env.ref('internal_transfer_voucher.view_payment_voucher_form').id,
                'target': 'new',
                'context': {
                    'default_company_id': company.id,
                    'default_partner_id': partner.id,
                    'default_amount': amount,
                    'default_currency_id': self.currency_id.id,
                    'default_account_id': counterpart.account_id.id,
                    'default_bill_ids': [(6, 0, self.ids)],
                    'default_description': _('Payment for %s') % (self.name or self.ref or ''),
                },
            }

        counterpart = self.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )[:1]
        if not counterpart:
            raise UserError(_("No open receivable account line was found on this customer invoice."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Receipt Voucher'),
            'res_model': 'account.receipt.voucher',
            'view_mode': 'form',
            'view_id': self.env.ref('internal_transfer_voucher.view_receipt_voucher_form').id,
            'target': 'new',
            'context': {
                'default_company_id': company.id,
                'default_partner_id': partner.id,
                'default_amount': amount,
                'default_currency_id': self.currency_id.id,
                'default_account_id': counterpart.account_id.id,
                'default_invoice_ids': [(6, 0, self.ids)],
                'default_description': _('Receipt for %s') % (self.name or self.ref or ''),
            },
        }
