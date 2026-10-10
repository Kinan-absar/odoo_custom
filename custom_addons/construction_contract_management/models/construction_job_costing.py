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
        string='Other Accounting Cost',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Posted project costs coming from miscellaneous journal entries, expenses, payroll, petty cash and other non-vendor-bill accounting entries.',
    )
    actual_cost_amount = fields.Monetary(
        string='Actual Cost',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Negative analytic amounts converted to a positive project cost.',
    )
    actual_revenue_amount = fields.Monetary(
        string='Actual Revenue',
        currency_field='currency_id',
        compute='_compute_job_costing',
        help='Positive analytic amounts posted to the selected analytic account.',
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
        for rec in records:
            if rec.project_id and 'account_id' in rec.project_id._fields:
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
        """Return posted P&L journal items allocated to this job.

        Reading account.move.line directly makes the job-cost actuals include
        vendor bills, miscellaneous journal entries, expenses, payroll journals,
        petty-cash journals and any other posted accounting entry carrying the
        project's analytic distribution.
        """
        self.ensure_one()
        if not self.analytic_account_id:
            return self.env['account.move.line']

        pnl_types = [
            'expense', 'expense_depreciation', 'expense_direct_cost',
            'income', 'income_other',
        ]
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
            ('account_id.account_type', 'in', pnl_types),
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
            rec.cost_exposure_amount = 0.0
            rec.forecast_final_cost = 0.0
            rec.forecast_profit = 0.0
            rec.forecast_margin_percent = 0.0
            rec.budget_variance = 0.0
            rec.budget_consumed_percent = 0.0

            if not rec.analytic_account_id:
                continue

            # Posted journal items are the accounting source of truth. This
            # includes vendor bills AND miscellaneous entries, expenses, payroll,
            # petty cash and other posted P&L entries carrying the project's
            # analytic allocation. Balance is expressed in company currency.
            vendor_bill_cost = 0.0
            other_accounting_cost = 0.0
            actual_cost = 0.0
            actual_revenue = 0.0
            advance_move_ids = set(rec.env['construction.advance'].search([
                ('contract_id', '=', rec.id),
                ('move_id', '!=', False),
            ]).mapped('move_id').ids)
            for line in rec._matching_account_move_lines(advance_move_ids):
                allocation = rec._job_cost_line_allocation(line, advance_move_ids)
                if not allocation:
                    continue
                allocated_balance = line.balance * allocation
                amount = rec._convert_job_cost_amount(
                    allocated_balance,
                    rec.company_id.currency_id,
                    line.date,
                )
                account_type = line.account_id.account_type
                if account_type in ('expense', 'expense_depreciation', 'expense_direct_cost'):
                    # Expense debits increase cost; credits/refunds reduce it.
                    actual_cost += amount
                    if line.move_id.move_type in ('in_invoice', 'in_refund'):
                        vendor_bill_cost += amount
                    else:
                        other_accounting_cost += amount
                elif account_type in ('income', 'income_other'):
                    # Income is normally a credit (negative balance).
                    actual_revenue += -amount

            rec.vendor_bill_cost_amount = max(vendor_bill_cost, 0.0)
            rec.other_accounting_cost_amount = max(other_accounting_cost, 0.0)
            rec.actual_cost_amount = max(vendor_bill_cost, 0.0) + max(other_accounting_cost, 0.0)
            rec.actual_revenue_amount = max(actual_revenue, 0.0)

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

    def action_view_job_cost_analytic_items(self):
        self.ensure_one()
        if not self.analytic_account_id:
            raise UserError(_('Set a Job Cost Analytic Account first.'))
        lines = self._matching_account_move_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Cost Accounting Lines'),
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
