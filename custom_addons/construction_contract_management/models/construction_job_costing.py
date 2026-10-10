from odoo import api, fields, models, _
from odoo.exceptions import UserError


def _distribution_has_account(distribution, account_id):
    """Return the percentage allocated to an analytic account in a distribution."""
    if not distribution or not account_id:
        return 0.0
    target = str(account_id)
    percentage = 0.0
    for key, value in distribution.items():
        account_ids = [part.strip() for part in str(key).split(',') if part.strip()]
        if target in account_ids:
            percentage += float(value or 0.0)
    return percentage


def _job_costing_bucket(move_type, move_id, account_id, advance_move_ids, advance_account_id):
    """Classify posted project journal items without treating advances as sales.

    Customer advance invoices and related refunds are not earned income.
    Their full invoice and related advance-account credits must not inflate
    actual invoice revenue; recovered advances posted through miscellaneous
    accounting entries are kept separately in the actual revenue calculation.
    """
    if move_type in ('in_invoice', 'in_refund', 'in_receipt'):
        return 'vendor'
    if move_type in ('out_invoice', 'out_refund', 'out_receipt'):
        if move_id in advance_move_ids or (advance_account_id and account_id == advance_account_id):
            return None
        return 'invoice'
    if move_type == 'entry':
        return 'miscellaneous'
    return None


def _is_customer_invoice_revenue_line(display_type, account_type, account_id,
                                      advance_account_id, retention_account_id):
    """Include only work lines from customer invoices, not invoice balancing lines.

    Odoo 18 invoice lines use display_type='product'. The tax and payment-term
    (receivable) lines have separate display types and must never be counted
    as sales. The customer advance and retention accounts are balance-sheet
    postings, not earned revenue, even when they occur on an invoice line.

    Do not require an income account here: existing IPC work accounts can be
    classified differently in a company's chart of accounts.
    """
    if display_type != 'product':
        return False
    if not account_id:
        return False
    if advance_account_id and account_id == advance_account_id:
        return False
    if retention_account_id and account_id == retention_account_id:
        return False
    if account_type in (
        'asset_receivable', 'asset_cash', 'liability_payable',
        'liability_current', 'liability_non_current', 'liability_credit_card',
    ):
        return False
    return True


def _project_journal_category(move_type, move_id, account_id, display_type,
                              account_type, advance_move_ids,
                              advance_account_id, retention_account_id,
                              is_tax_line=False):
    """One definition for both the profitability totals and journal-item drill-down.

    Never show or count an advance invoice's liability/VAT/receivable entries
    as project income. Do retain real IPC invoice lines even if the company's
    work-revenue account is configured with a non-income account type.
    """
    bucket = _job_costing_bucket(
        move_type, move_id, account_id, advance_move_ids, advance_account_id,
    )
    if bucket != 'invoice':
        return bucket
    if is_tax_line:
        return None
    if _is_customer_invoice_revenue_line(
        display_type, account_type, account_id,
        advance_account_id, retention_account_id,
    ):
        return 'invoice'
    return None


class ConstructionContractJobCosting(models.Model):
    _inherit = 'construction.contract'

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Job Cost Analytic Account',
        tracking=True,
        check_company=True,
        help='Analytic account used to collect the actual revenue and cost of this construction contract.',
    )
    job_cost_budget = fields.Monetary(
        string='Cost Budget',
        currency_field='currency_id',
        tracking=True,
        help='Approved/target total cost budget for this contract. This is a management value; accounting actuals are read from the analytic account.',
    )
    forecast_remaining_cost = fields.Monetary(
        string='Uncommitted Forecast Cost',
        currency_field='currency_id',
        tracking=True,
        help='Expected future cost that is not yet represented by posted actuals or confirmed purchase commitments.',
    )
    purchase_commitment_amount = fields.Monetary(
        string='PO Commitments',
        currency_field='currency_id',
        compute='_compute_job_costing',
    )
    purchase_billed_amount = fields.Monetary(
        string='PO Billed Cost',
        currency_field='currency_id',
        compute='_compute_job_costing',
    )
    open_purchase_commitment = fields.Monetary(
        string='Open PO Commitment',
        currency_field='currency_id',
        compute='_compute_job_costing',
    )
    vendor_bill_cost_amount = fields.Monetary(
        string='Vendor Bill Cost',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Posted vendor bills and vendor credit notes allocated to this project, whether or not they originate from a Purchase Order.',
    )
    other_accounting_cost_amount = fields.Monetary(
        string='Overhead',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Total allocated debits from posted miscellaneous journal entries (move type entry).',
    )
    actual_cost_amount = fields.Monetary(
        string='Actual Cost',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Vendor Bills debit minus Vendor Bills credit, plus Miscellaneous Operations debit, for this project.',
    )
    actual_revenue_amount = fields.Monetary(
        string='Actual Revenue',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Net customer invoice work revenue (invoice credits less credit-note debits, excluding customer advances) plus recovered-advance credits from miscellaneous entries.',
    )
    invoice_revenue_credit_amount = fields.Monetary(
        string='Customer Invoice Revenue (Net of Credit Notes)',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Posted work invoice credits less customer credit-note work-line debits; excludes advances, VAT, receivables, and retention.',
    )
    miscellaneous_revenue_credit_amount = fields.Monetary(
        string='Customer Advance Recovered',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Allocated credits on posted miscellaneous accounting entries representing recovered customer advances, as shown in the project journal items.',
    )
    actual_profit_amount = fields.Monetary(
        string='Actual Profit',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Actual Revenue minus Actual Cost. Based on posted accounting entries only.',
    )
    actual_profit_margin_percent = fields.Float(
        string='Actual Profit Margin %',
        digits=(16, 2),
        compute='_compute_job_costing',
        help='Actual Profit divided by Actual Revenue, multiplied by 100.',
    )
    cost_exposure_amount = fields.Monetary(
        string='Cost Exposure',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Actual cost plus open purchase commitments.',
    )
    forecast_final_cost = fields.Monetary(
        string='Forecast Final Cost',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Actual cost + open PO commitments + uncommitted forecast cost.',
    )
    forecast_profit = fields.Monetary(
        string='Forecast Profit',
        currency_field='currency_id',
        compute='_compute_job_costing',
    )
    forecast_margin_percent = fields.Float(
        string='Forecast Margin %',
        compute='_compute_job_costing',
    )
    budget_variance = fields.Monetary(
        string='Cost Budget Variance',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Cost Budget minus Forecast Final Cost. Negative means forecast cost exceeds budget.',
    )
    budget_consumed_percent = fields.Float(
        string='Budget Consumed %',
        compute='_compute_job_costing',
    )

    @api.onchange('project_id')
    def _onchange_project_job_cost_analytic(self):
        for rec in self:
            if rec.project_id and 'account_id' in rec.project_id._fields:
                rec.analytic_account_id = rec.project_id.account_id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            if 'analytic_account_id' not in vals and rec.project_id and 'account_id' in rec.project_id._fields:
                rec.analytic_account_id = rec.project_id.account_id
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'project_id' in vals and 'analytic_account_id' not in vals:
            for rec in self:
                if rec.project_id and 'account_id' in rec.project_id._fields:
                    rec.analytic_account_id = rec.project_id.account_id
        return result

    def _convert_job_cost_amount(self, amount, source_currency, date=False):
        self.ensure_one()
        source_currency = source_currency or self.company_id.currency_id
        if source_currency == self.currency_id:
            return amount
        return source_currency._convert(
            amount,
            self.currency_id,
            self.company_id,
            date or fields.Date.context_today(self),
        )

    def _analytic_line_domain(self):
        self.ensure_one()
        analytic = self.analytic_account_id
        if not analytic:
            return []
        plan = analytic.plan_id
        if not plan:
            return []
        column = plan._column_name()
        return [(column, '=', analytic.id), ('company_id', '=', self.company_id.id)]

    def _matching_account_move_lines(self, advance_move_ids=None):
        """Return posted journal lines allocated to the selected project.

        All account types must be eligible: the requested totals come from the
        Debit and Credit columns, not just P&L account classifications.
        The journal-item drill-down later applies the SAME category filter used
        by the profitability compute, excluding customer invoice balance lines.
        """
        self.ensure_one()
        if not self.analytic_account_id:
            return self.env['account.move.line']

        # Existing Construction Advance moves may predate the contract-tagging
        # enhancement below, so include them explicitly by their linked move.
        # Resolve this once per contract; never query again for every journal line.
        if advance_move_ids is None:
            advance_move_ids = self.env['construction.advance'].search([
                ('contract_id', '=', self.id),
                ('move_id', '!=', False),
            ]).mapped('move_id').ids
        advance_move_ids = set(advance_move_ids)
        advance_move_id_list = list(advance_move_ids)

        allocation_domain = [
            '|',
            '|',
            ('analytic_distribution', '!=', False),
            ('move_id.construction_contract_id', '=', self.id),
            ('purchase_line_id', '!=', False),
        ]
        if advance_move_id_list:
            allocation_domain = ['|', ('move_id', 'in', advance_move_id_list)] + allocation_domain

        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('move_id.state', '=', 'posted'),
        ] + allocation_domain)

        # Use the same allocation routine as the computation itself. Besides
        # direct analytic allocation, it also recognizes entries explicitly
        # tagged with this contract and vendor-bill lines linked to PO lines
        # carrying the project's analytic distribution.
        return lines.filtered(lambda line: self._job_cost_line_allocation(line, advance_move_ids) > 0.0)

    def _job_cost_line_allocation(self, line, advance_move_ids=None):
        self.ensure_one()
        if not self.analytic_account_id:
            return 0.0
        percentage = _distribution_has_account(
            line.analytic_distribution,
            self.analytic_account_id.id,
        )
        if percentage:
            return percentage / 100.0
        if line.move_id.construction_contract_id == self and not line.analytic_distribution:
            return 1.0
        # Backward compatibility for Construction Advance accounting moves that
        # were created before account.move was stamped with the contract.
        # advance_move_ids is preloaded once to avoid one SQL query per journal line.
        if advance_move_ids and line.move_id.id in advance_move_ids:
            return 1.0
        # Vendor bill lines generated from a PO do not always keep an
        # analytic_distribution on the invoice line itself. In that case,
        # inherit the project allocation from the originating PO line.
        if getattr(line, 'purchase_line_id', False):
            percentage = _distribution_has_account(
                line.purchase_line_id.analytic_distribution,
                self.analytic_account_id.id,
            )
            if percentage:
                return percentage / 100.0
        return 0.0

    def _job_cost_journal_category(self, line, advance_move_ids,
                                   advance_account_id, retention_account_id):
        """Used by totals AND drill-down so they cannot disagree."""
        self.ensure_one()
        return _project_journal_category(
            line.move_id.move_type, line.move_id.id, line.account_id.id,
            line.display_type, line.account_id.account_type,
            advance_move_ids, advance_account_id, retention_account_id,
            bool(line.tax_line_id),
        )

    def _matching_purchase_lines(self):
        self.ensure_one()
        if not self.analytic_account_id:
            return self.env['purchase.order.line']
        lines = self.env['purchase.order.line'].search([
            ('order_id.company_id', '=', self.company_id.id),
            ('order_id.state', 'in', ['purchase', 'done']),
            ('display_type', '=', False),
        ])
        analytic_id = self.analytic_account_id.id
        return lines.filtered(lambda line: _distribution_has_account(line.analytic_distribution, analytic_id) > 0.0)

    @api.depends('analytic_account_id', 'job_cost_budget', 'forecast_remaining_cost', 'revised_amount', 'currency_id', 'company_id')
    def _compute_job_costing(self):
        for rec in self:
            rec.purchase_commitment_amount = 0.0
            rec.purchase_billed_amount = 0.0
            rec.open_purchase_commitment = 0.0
            rec.vendor_bill_cost_amount = 0.0
            rec.other_accounting_cost_amount = 0.0
            rec.actual_cost_amount = 0.0
            rec.actual_revenue_amount = 0.0
            rec.actual_profit_amount = 0.0
            rec.actual_profit_margin_percent = 0.0
            rec.invoice_revenue_credit_amount = 0.0
            rec.miscellaneous_revenue_credit_amount = 0.0
            rec.cost_exposure_amount = 0.0
            rec.forecast_final_cost = 0.0
            rec.forecast_profit = 0.0
            rec.forecast_margin_percent = 0.0
            rec.budget_variance = 0.0
            rec.budget_consumed_percent = 0.0

            if not rec.analytic_account_id:
                continue

            # Reconcile directly with the Debit/Credit columns in the journal
            # items list grouped by document type.  Do not filter by account
            # type: the user wants the shown gross posted debit/credit totals.
            vendor_bill_debits = 0.0
            vendor_bill_credits = 0.0
            miscellaneous_debits = 0.0
            miscellaneous_credits = 0.0
            invoice_credits = 0.0
            invoice_debits = 0.0
            advance_move_ids = set(rec.env['construction.advance'].search([
                ('contract_id', '=', rec.id),
                ('move_id', '!=', False),
            ]).mapped('move_id').ids)
            advance_account_id = rec.advance_account_id.id if rec.advance_account_id else False
            retention_account_id = rec.retention_account_id.id if rec.retention_account_id else False
            for line in rec._matching_account_move_lines(advance_move_ids):
                allocation = rec._job_cost_line_allocation(line, advance_move_ids)
                if not allocation:
                    continue
                debit = rec._convert_job_cost_amount(
                    line.debit * allocation, rec.company_id.currency_id, line.date,
                )
                credit = rec._convert_job_cost_amount(
                    line.credit * allocation, rec.company_id.currency_id, line.date,
                )
                bucket = rec._job_cost_journal_category(
                    line, advance_move_ids, advance_account_id,
                    retention_account_id,
                )
                if bucket == 'vendor':
                    vendor_bill_debits += debit
                    vendor_bill_credits += credit
                elif bucket == 'invoice':
                    invoice_credits += credit
                    invoice_debits += debit
                elif bucket == 'miscellaneous':
                    miscellaneous_debits += debit
                    miscellaneous_credits += credit

            rec.vendor_bill_cost_amount = vendor_bill_debits - vendor_bill_credits
            rec.other_accounting_cost_amount = miscellaneous_debits
            rec.actual_cost_amount = rec.vendor_bill_cost_amount + miscellaneous_debits
            rec.invoice_revenue_credit_amount = invoice_credits - invoice_debits
            rec.miscellaneous_revenue_credit_amount = miscellaneous_credits
            rec.actual_revenue_amount = rec.invoice_revenue_credit_amount + miscellaneous_credits
            rec.actual_profit_amount = rec.actual_revenue_amount - rec.actual_cost_amount
            rec.actual_profit_margin_percent = (
                rec.actual_profit_amount / rec.actual_revenue_amount * 100.0
                if rec.actual_revenue_amount else 0.0
            )

            # Purchase commitment is based on confirmed PO lines carrying this
            # analytic account. No Inventory/stock records are required.
            purchase_lines = rec._matching_purchase_lines()
            commitment = 0.0
            billed = 0.0
            for po_line in purchase_lines:
                allocation = _distribution_has_account(
                    po_line.analytic_distribution,
                    rec.analytic_account_id.id,
                ) / 100.0
                if not allocation:
                    continue

                po_date = po_line.order_id.date_order.date() if po_line.order_id.date_order else False
                line_commitment = rec._convert_job_cost_amount(
                    po_line.price_subtotal * allocation,
                    po_line.order_id.currency_id,
                    po_date,
                )
                commitment += line_commitment

                for invoice_line in po_line.invoice_lines.filtered(
                    lambda l: l.move_id.state == 'posted' and l.move_id.move_type in ('in_invoice', 'in_refund')
                ):
                    # Balance is in company currency and naturally reverses for refunds.
                    line_allocation = _distribution_has_account(
                        invoice_line.analytic_distribution,
                        rec.analytic_account_id.id,
                    ) / 100.0
                    if not line_allocation:
                        line_allocation = allocation
                    amount_company = invoice_line.balance * line_allocation
                    billed += rec._convert_job_cost_amount(
                        amount_company,
                        rec.company_id.currency_id,
                        invoice_line.date,
                    )

            rec.purchase_commitment_amount = commitment
            rec.purchase_billed_amount = max(billed, 0.0)
            rec.open_purchase_commitment = max(commitment - billed, 0.0)
            rec.cost_exposure_amount = rec.actual_cost_amount + rec.open_purchase_commitment
            rec.forecast_final_cost = rec.cost_exposure_amount + (rec.forecast_remaining_cost or 0.0)

            revenue_base = rec.revised_amount or rec.original_amount or 0.0
            rec.forecast_profit = revenue_base - rec.forecast_final_cost
            rec.forecast_margin_percent = (
                rec.forecast_profit / revenue_base * 100.0 if revenue_base else 0.0
            )
            rec.budget_variance = (rec.job_cost_budget or 0.0) - rec.forecast_final_cost
            rec.budget_consumed_percent = (
                rec.actual_cost_amount / rec.job_cost_budget * 100.0
                if rec.job_cost_budget else 0.0
            )

    def action_use_project_analytic_account(self):
        """Backward-compatible action for views stored in existing databases.

        Never create an analytic account; only reuse the project's existing one.
        """
        self.ensure_one()
        if self.project_id and 'account_id' in self.project_id._fields:
            self.analytic_account_id = self.project_id.account_id or False
        return True

    def action_view_job_cost_analytic_items(self):
        self.ensure_one()
        if not self.analytic_account_id:
            raise UserError(_('Set a Job Cost Analytic Account first.'))
        advance_move_ids = set(self.env['construction.advance'].search([
            ('contract_id', '=', self.id),
            ('move_id', '!=', False),
        ]).mapped('move_id').ids)
        advance_account_id = self.advance_account_id.id if self.advance_account_id else False
        retention_account_id = self.retention_account_id.id if self.retention_account_id else False
        lines = self._matching_account_move_lines(advance_move_ids).filtered(
            lambda line: bool(self._job_cost_journal_category(
                line, advance_move_ids, advance_account_id, retention_account_id,
            ))
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Project Cost & Revenue Journal Lines'),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', lines.ids)],
            'context': {'default_company_id': self.company_id.id},
        }

    def action_view_job_cost_purchase_orders(self):
        self.ensure_one()
        purchase_lines = self._matching_purchase_lines()
        orders = purchase_lines.mapped('order_id')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Cost Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', orders.ids)],
            'context': {
                'default_company_id': self.company_id.id,
            },
        }


class AccountMoveConstructionJobCost(models.Model):
    _inherit = 'account.move'

    construction_contract_id = fields.Many2one(
        'construction.contract',
        string='Construction Contract',
        domain="[('company_id', '=', company_id)]",
        tracking=True,
        help='Construction contract/project used to allocate this accounting entry to job costing.',
    )

    @api.onchange('construction_contract_id')
    def _onchange_construction_contract_id(self):
        for move in self:
            move._apply_construction_analytic_to_lines()

    def _apply_construction_analytic_to_lines(self):
        pnl_types = {
            'expense', 'expense_depreciation', 'expense_direct_cost',
            'income', 'income_other',
        }
        for move in self:
            analytic = move.construction_contract_id.analytic_account_id
            if not analytic:
                continue
            for line in move.line_ids.filtered(
                lambda l: l.account_id
                and l.account_id.account_type in pnl_types
                and not l.analytic_distribution
            ):
                line.analytic_distribution = {str(analytic.id): 100.0}

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._apply_construction_analytic_to_lines()
        return moves

    def write(self, vals):
        result = super().write(vals)
        if 'construction_contract_id' in vals and not self.env.context.get('ccm_skip_analytic_apply'):
            self.with_context(ccm_skip_analytic_apply=True)._apply_construction_analytic_to_lines()
        return result


class AccountMoveLineConstructionJobCost(models.Model):
    _inherit = 'account.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        pnl_types = {
            'expense', 'expense_depreciation', 'expense_direct_cost',
            'income', 'income_other',
        }
        for line in lines:
            move = line.move_id
            contract = move.construction_contract_id
            analytic = contract.analytic_account_id if contract else False
            if (
                analytic
                and line.account_id
                and line.account_id.account_type in pnl_types
                and not line.analytic_distribution
                and move.state == 'draft'
            ):
                line.with_context(check_move_validity=False).analytic_distribution = {str(analytic.id): 100.0}
        return lines
