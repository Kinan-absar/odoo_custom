from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    payment_voucher_count = fields.Integer(compute='_compute_payment_voucher_count', string='Payment Vouchers')

    # Reverse the vouchers' existing move_id relation. This also covers entries
    # posted before this field was introduced, without matching reference text.
    source_payment_voucher_ids = fields.One2many(
        'account.payment.voucher', 'move_id', readonly=True, copy=False,
    )
    source_receipt_voucher_ids = fields.One2many(
        'account.receipt.voucher', 'move_id', readonly=True, copy=False,
    )
    source_payment_voucher_id = fields.Many2one(
        'account.payment.voucher', string='Payment Voucher',
        compute='_compute_source_vouchers', compute_sudo=False,
    )
    source_receipt_voucher_id = fields.Many2one(
        'account.receipt.voucher', string='Receipt Voucher',
        compute='_compute_source_vouchers', compute_sudo=False,
    )

    @api.depends('move_type', 'source_payment_voucher_ids', 'source_receipt_voucher_ids')
    @api.depends_context('uid')
    def _compute_source_vouchers(self):
        entries = self.filtered(lambda move: move.move_type == 'entry')
        linked = {}
        for model, field in (
            ('account.payment.voucher', 'source_payment_voucher_id'),
            ('account.receipt.voucher', 'source_receipt_voucher_id'),
        ):
            by_move = {}
            Voucher = self.env[model]
            if entries and Voucher.check_access_rights('read', raise_exception=False):
                for voucher in Voucher.search([('move_id', 'in', entries.ids)], order='id'):
                    by_move.setdefault(voucher.move_id.id, voucher)
            linked[field] = by_move
        for move in self:
            move.source_payment_voucher_id = linked['source_payment_voucher_id'].get(move.id, False)
            move.source_receipt_voucher_id = linked['source_receipt_voucher_id'].get(move.id, False)

    def _get_linked_payment_vouchers(self):
        """Return custom payment vouchers linked to this bill, including already-reconciled ones.

        After a voucher is reconciled, ``bill_ids`` can be cleared by the voucher workflow.
        Therefore the smart button must also follow the accounting reconciliation from the
        bill payable line to the voucher's posted journal entry.
        """
        self.ensure_one()
        Voucher = self.env['account.payment.voucher']
        if self.move_type != 'in_invoice':
            return Voucher.browse()

        vouchers = Voucher.search([('bill_ids', 'in', self.id)])
        payable_lines = self.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
        )
        if payable_lines:
            partials = self.env['account.partial.reconcile'].search([
                '|',
                ('debit_move_id', 'in', payable_lines.ids),
                ('credit_move_id', 'in', payable_lines.ids),
            ])
            opposite_lines = (partials.mapped('debit_move_id') | partials.mapped('credit_move_id')) - payable_lines
            counterpart_moves = opposite_lines.mapped('move_id')
            if counterpart_moves:
                vouchers |= Voucher.search([('move_id', 'in', counterpart_moves.ids)])
        return vouchers

    def _compute_payment_voucher_count(self):
        for move in self:
            move.payment_voucher_count = len(move._get_linked_payment_vouchers()) if move.move_type == 'in_invoice' else 0

    def action_view_payment_vouchers(self):
        self.ensure_one()
        vouchers = self._get_linked_payment_vouchers()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Payment Vouchers'),
            'res_model': 'account.payment.voucher',
            'view_mode': 'list,form',
            'domain': [('id', 'in', vouchers.ids)],
            'context': {'default_partner_id': self.commercial_partner_id.id, 'default_bill_ids': [(6, 0, self.ids)]},
        }
        if len(vouchers) == 1:
            action.update({'view_mode': 'form', 'res_id': vouchers.id})
        return action

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
