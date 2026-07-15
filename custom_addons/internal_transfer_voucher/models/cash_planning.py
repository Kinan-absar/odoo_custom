from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CashPlanCategory(models.Model):
    _name = 'cash.plan.category'
    _description = 'Cash Planning Category'
    _order = 'flow_type, sequence, name'

    name = fields.Char(required=True, translate=True)
    flow_type = fields.Selection([('in', 'Cash Inflow'), ('out', 'Cash Outflow')], required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)


class CashPlanRun(models.Model):
    _name = 'cash.plan.run'
    _description = 'Weekly Cash Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    opening_balance = fields.Monetary(tracking=True)
    budget_amount = fields.Monetary(string='Weekly Payment Budget', tracking=True)
    notes = fields.Html()
    line_ids = fields.One2many('cash.plan.line', 'run_id', copy=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Submitted'), ('approved', 'Approved'),
        ('in_progress', 'In Progress'), ('done', 'Completed'), ('cancel', 'Cancelled')
    ], default='draft', tracking=True)

    forecast_inflow = fields.Monetary(compute='_compute_totals', store=True)
    forecast_outflow = fields.Monetary(compute='_compute_totals', store=True)
    actual_inflow = fields.Monetary(compute='_compute_totals', store=True)
    actual_outflow = fields.Monetary(compute='_compute_totals', store=True)
    forecast_net = fields.Monetary(compute='_compute_totals', store=True)
    actual_net = fields.Monetary(compute='_compute_totals', store=True)
    forecast_closing = fields.Monetary(compute='_compute_totals', store=True)
    actual_closing = fields.Monetary(compute='_compute_totals', store=True)
    forecast_variance = fields.Monetary(compute='_compute_totals', store=True)
    budget_remaining = fields.Monetary(compute='_compute_totals', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('cash.plan.run') or 'New'
        return super().create(vals_list)

    @api.depends('opening_balance', 'budget_amount', 'line_ids.flow_type', 'line_ids.forecast_amount',
                 'line_ids.actual_amount', 'line_ids.state')
    def _compute_totals(self):
        for rec in self:
            active_lines = rec.line_ids.filtered(lambda l: l.state != 'cancel')
            rec.forecast_inflow = sum(active_lines.filtered(lambda l: l.flow_type == 'in').mapped('forecast_amount'))
            rec.forecast_outflow = sum(active_lines.filtered(lambda l: l.flow_type == 'out').mapped('forecast_amount'))
            rec.actual_inflow = sum(active_lines.filtered(lambda l: l.flow_type == 'in').mapped('actual_amount'))
            rec.actual_outflow = sum(active_lines.filtered(lambda l: l.flow_type == 'out').mapped('actual_amount'))
            rec.forecast_net = rec.forecast_inflow - rec.forecast_outflow
            rec.actual_net = rec.actual_inflow - rec.actual_outflow
            rec.forecast_closing = rec.opening_balance + rec.forecast_net
            rec.actual_closing = rec.opening_balance + rec.actual_net
            rec.forecast_variance = rec.actual_closing - rec.forecast_closing
            rec.budget_remaining = rec.budget_amount - rec.forecast_outflow if rec.budget_amount else 0.0

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to < rec.date_from:
                raise ValidationError(_('End date cannot be before start date.'))

    def action_submit(self): self.write({'state': 'submitted'})
    def action_approve(self): self.write({'state': 'approved'})
    def action_start(self): self.write({'state': 'in_progress'})
    def action_done(self): self.write({'state': 'done'})
    def action_cancel(self): self.write({'state': 'cancel'})
    def action_draft(self): self.write({'state': 'draft'})


class CashPlanLine(models.Model):
    _name = 'cash.plan.line'
    _description = 'Cash Planning Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'planned_date, priority, id'

    name = fields.Char(required=True, tracking=True, default=lambda self: _('Planned Cash Movement'))
    run_id = fields.Many2one('cash.plan.run', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='run_id.company_id', store=True)
    currency_id = fields.Many2one(related='run_id.currency_id', store=True)
    planned_date = fields.Date(required=True, tracking=True)
    flow_type = fields.Selection([('out', 'Payment'), ('in', 'Receipt')], required=True, tracking=True)
    transaction_type = fields.Selection([
        ('supplier', 'Supplier / Subcontractor'), ('expense', 'Expense'), ('payroll', 'Payroll / Manpower'),
        ('cash', 'Cash Withdrawal / Deposit'), ('transfer', 'Journal Transfer'), ('loan', 'Loan / Financing'),
        ('customer', 'Customer Collection'), ('revenue', 'Sales / Revenue'), ('other', 'Other')
    ], required=True, default='supplier', tracking=True)
    category_id = fields.Many2one('cash.plan.category', required=True, domain="[('flow_type', '=', flow_type), '|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    partner_id = fields.Many2one('res.partner', tracking=True)
    project_id = fields.Many2one('project.project', tracking=True)
    forecast_amount = fields.Monetary(required=True, tracking=True)
    actual_amount = fields.Monetary(compute='_compute_actual', store=True)
    variance_amount = fields.Monetary(compute='_compute_actual', store=True)
    priority = fields.Selection([('0', 'Low'), ('1', 'Normal'), ('2', 'High'), ('3', 'Urgent')], default='1', tracking=True)
    funding_status = fields.Selection([('funded', 'Funded'), ('partial', 'Partially Funded'), ('unfunded', 'Not Funded')], default='funded', tracking=True)
    journal_id = fields.Many2one('account.journal', domain="[('company_id', '=', company_id), ('default_account_id', '!=', False)]")
    destination_journal_id = fields.Many2one('account.journal', domain="[('company_id', '=', company_id), ('default_account_id', '!=', False)]")
    account_id = fields.Many2one('account.account', domain="[('company_ids', 'in', company_id)]")
    purchase_order_ids = fields.Many2many('purchase.order', string='Purchase Orders', domain="[('partner_id', '=', partner_id), ('company_id', '=', company_id)]")
    bill_ids = fields.Many2many('account.move', 'cash_plan_line_bill_rel', 'line_id', 'move_id', string='Vendor Bills', domain="[('partner_id', '=', partner_id), ('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), ('company_id', '=', company_id)]")
    invoice_ids = fields.Many2many('account.move', 'cash_plan_line_invoice_rel', 'line_id', 'move_id', string='Customer Invoices', domain="[('partner_id', '=', partner_id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('company_id', '=', company_id)]")
    description = fields.Text()
    state = fields.Selection([('planned', 'Planned'), ('approved', 'Approved'), ('executed', 'Executed'), ('cancel', 'Cancelled')], default='planned', tracking=True)
    payment_voucher_id = fields.Many2one('account.payment.voucher', readonly=True, copy=False)
    receipt_voucher_id = fields.Many2one('account.receipt.voucher', readonly=True, copy=False)
    internal_transfer_id = fields.Many2one('account.internal.transfer', readonly=True, copy=False)

    @api.depends('payment_voucher_id.state', 'payment_voucher_id.amount', 'receipt_voucher_id.state',
                 'receipt_voucher_id.amount', 'internal_transfer_id.state', 'internal_transfer_id.amount', 'forecast_amount')
    def _compute_actual(self):
        for rec in self:
            actual = 0.0
            if rec.payment_voucher_id and rec.payment_voucher_id.state == 'posted':
                actual = rec.payment_voucher_id.amount
            elif rec.receipt_voucher_id and rec.receipt_voucher_id.state == 'posted':
                actual = rec.receipt_voucher_id.amount
            elif rec.internal_transfer_id and rec.internal_transfer_id.state == 'posted':
                actual = rec.internal_transfer_id.amount
            rec.actual_amount = actual
            rec.variance_amount = actual - rec.forecast_amount

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = self._prepare_default_name(vals)
        return super().create(vals_list)

    def write(self, vals):
        if 'name' in vals and not vals.get('name'):
            vals['name'] = _('Planned Cash Movement')
        return super().write(vals)

    @api.onchange('category_id', 'partner_id', 'transaction_type', 'flow_type')
    def _onchange_planning_name(self):
        for rec in self:
            if not rec.name or rec.name == _('Planned Cash Movement'):
                parts = []
                if rec.category_id:
                    parts.append(rec.category_id.display_name)
                elif rec.transaction_type:
                    parts.append(dict(rec._fields['transaction_type'].selection).get(rec.transaction_type))
                if rec.partner_id:
                    parts.append(rec.partner_id.display_name)
                rec.name = ' - '.join(filter(None, parts)) or _('Planned Cash Movement')

    def _prepare_default_name(self, vals):
        parts = []
        category_id = vals.get('category_id')
        partner_id = vals.get('partner_id')
        transaction_type = vals.get('transaction_type')
        if category_id:
            category = self.env['cash.plan.category'].browse(category_id).exists()
            if category:
                parts.append(category.display_name)
        elif transaction_type:
            parts.append(dict(self._fields['transaction_type'].selection).get(transaction_type))
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id).exists()
            if partner:
                parts.append(partner.display_name)
        return ' - '.join(filter(None, parts)) or _('Planned Cash Movement')

    @api.constrains('forecast_amount')
    def _check_amount(self):
        for rec in self:
            if rec.forecast_amount <= 0:
                raise ValidationError(_('Forecast amount must be greater than zero.'))

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_execute(self):
        self.ensure_one()
        if self.state == 'cancel':
            raise UserError(_('Cancelled planning lines cannot be executed.'))
        if self.payment_voucher_id or self.receipt_voucher_id or self.internal_transfer_id:
            return self.action_open_document()
        if not self.journal_id:
            raise UserError(_('Select the expected journal before execution.'))

        common = {
            'date': self.planned_date,
            'amount': self.forecast_amount,
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'description': self.description or self.name,
        }
        action = False
        if self.transaction_type == 'transfer':
            if not self.destination_journal_id:
                raise UserError(_('Select a destination journal.'))
            transfer = self.env['account.internal.transfer'].create({
                **common, 'source_journal_id': self.journal_id.id,
                'line_ids': [(0, 0, {'journal_id': self.destination_journal_id.id, 'amount': self.forecast_amount})],
            })
            self.internal_transfer_id = transfer
            action = self._document_action('account.internal.transfer', transfer.id)
        elif self.flow_type == 'out':
            if not self.partner_id:
                raise UserError(_('Select a partner for the planned payment.'))
            vals = {**common, 'partner_id': self.partner_id.id, 'journal_id': self.journal_id.id,
                    'account_id': self.account_id.id if self.account_id else False,
                    'bill_ids': [(6, 0, self.bill_ids.ids)], 'purchase_order_ids': [(6, 0, self.purchase_order_ids.ids)]}
            voucher = self.env['account.payment.voucher'].create(vals)
            self.payment_voucher_id = voucher
            action = self._document_action('account.payment.voucher', voucher.id)
        else:
            if not self.partner_id:
                raise UserError(_('Select a partner for the planned receipt.'))
            if not self.account_id:
                raise UserError(_('Select an income or receivable account.'))
            voucher = self.env['account.receipt.voucher'].create({
                **common, 'partner_id': self.partner_id.id, 'journal_id': self.journal_id.id,
                'account_id': self.account_id.id, 'invoice_ids': [(6, 0, self.invoice_ids.ids)]})
            self.receipt_voucher_id = voucher
            action = self._document_action('account.receipt.voucher', voucher.id)
        self.state = 'executed'
        return action

    def _document_action(self, model, res_id):
        return {'type': 'ir.actions.act_window', 'res_model': model, 'res_id': res_id,
                'view_mode': 'form', 'target': 'current'}

    def action_open_document(self):
        self.ensure_one()
        if self.payment_voucher_id:
            return self._document_action('account.payment.voucher', self.payment_voucher_id.id)
        if self.receipt_voucher_id:
            return self._document_action('account.receipt.voucher', self.receipt_voucher_id.id)
        if self.internal_transfer_id:
            return self._document_action('account.internal.transfer', self.internal_transfer_id.id)
        raise UserError(_('No executed voucher exists yet.'))
