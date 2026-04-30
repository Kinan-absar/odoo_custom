from odoo import api, fields, models


class ConstructionDashboard(models.Model):
    _name = 'construction.dashboard'
    _description = 'Construction Dashboard'

    name = fields.Char(default='Dashboard', required=True)

    selected_contract_id = fields.Many2one(
        'construction.contract',
        string='Contract Filter',
    )

    active_contract_count = fields.Integer(string='Active Contracts', compute='_compute_dashboard')
    total_revised_amount = fields.Monetary(string='Total Revised Amount', currency_field='currency_id', compute='_compute_dashboard')
    total_certified_amount = fields.Monetary(string='Total Certified', currency_field='currency_id', compute='_compute_dashboard')
    total_invoiced_amount = fields.Monetary(string='Total Invoiced / Billed', currency_field='currency_id', compute='_compute_dashboard')
    total_paid_amount = fields.Monetary(string='Total Paid', currency_field='currency_id', compute='_compute_dashboard')
    total_advance_balance = fields.Monetary(string='Advance Balance', currency_field='currency_id', compute='_compute_dashboard')
    total_retention_balance = fields.Monetary(string='Retention Balance', currency_field='currency_id', compute='_compute_dashboard')

    pending_ipc_count = fields.Integer(string='Pending IPCs', compute='_compute_dashboard')
    pending_variation_count = fields.Integer(string='Pending Variations', compute='_compute_dashboard')
    pending_advance_count = fields.Integer(string='Pending Advances', compute='_compute_dashboard')
    pending_retention_release_count = fields.Integer(string='Pending Retention Releases', compute='_compute_dashboard')

    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency')

    @api.depends_context('uid')
    def _compute_currency(self):
        for rec in self:
            rec.currency_id = self.env.company.currency_id

    @api.depends(
        'selected_contract_id',
        'selected_contract_id.state',
        'selected_contract_id.revised_amount',
        'selected_contract_id.total_certified_amount',
        'selected_contract_id.total_move_amount',
        'selected_contract_id.total_paid_amount',
        'selected_contract_id.advance_balance',
        'selected_contract_id.retention_balance',
    )
    def _compute_dashboard(self):
        Contract = self.env['construction.contract']
        IPC = self.env['construction.ipc']
        Variation = self.env['construction.variation']
        Advance = self.env['construction.advance']
        RetentionRelease = self.env['construction.retention.release']

        for rec in self:
            if rec.selected_contract_id:
                contracts = rec.selected_contract_id
                contract_domain = [('id', '=', rec.selected_contract_id.id)]
                ipc_domain = [('contract_id', '=', rec.selected_contract_id.id)]
                variation_domain = [('contract_id', '=', rec.selected_contract_id.id)]
                advance_domain = [('contract_id', '=', rec.selected_contract_id.id)]
                retention_release_domain = [('contract_id', '=', rec.selected_contract_id.id)]
            else:
                contracts = Contract.search([])
                contract_domain = []
                ipc_domain = []
                variation_domain = []
                advance_domain = []
                retention_release_domain = []

            active_contracts = Contract.search(contract_domain + [('state', '=', 'active')])
            pending_ipcs = IPC.search(ipc_domain + [('state', 'in', ['draft', 'under_review'])])
            pending_variations = Variation.search(variation_domain + [('state', 'in', ['draft', 'submitted'])])
            pending_advances = Advance.search(advance_domain + [('state', '=', 'draft')])
            pending_retention_releases = RetentionRelease.search(retention_release_domain + [('state', '=', 'draft')])

            rec.active_contract_count = len(active_contracts)
            rec.total_revised_amount = sum(contracts.mapped('revised_amount'))
            rec.total_certified_amount = sum(contracts.mapped('total_certified_amount'))
            rec.total_invoiced_amount = sum(contracts.mapped('total_move_amount'))
            rec.total_paid_amount = sum(contracts.mapped('total_paid_amount'))
            rec.total_advance_balance = sum(contracts.mapped('advance_balance'))
            rec.total_retention_balance = sum(contracts.mapped('retention_balance'))

            rec.pending_ipc_count = len(pending_ipcs)
            rec.pending_variation_count = len(pending_variations)
            rec.pending_advance_count = len(pending_advances)
            rec.pending_retention_release_count = len(pending_retention_releases)

    def action_clear_contract_filter(self):
        self.ensure_one()
        self.selected_contract_id = False
        return {
            'type': 'ir.actions.act_window',
            'name': 'Dashboard',
            'res_model': 'construction.dashboard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_contracts(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Contracts',
            'res_model': 'construction.contract',
            'view_mode': 'list,form',
        }

    def action_open_active_contracts(self):
        domain = [('state', '=', 'active')]
        if self.selected_contract_id:
            domain.append(('id', '=', self.selected_contract_id.id))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Active Contracts',
            'res_model': 'construction.contract',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_open_pending_ipcs(self):
        domain = [('state', 'in', ['draft', 'under_review'])]
        if self.selected_contract_id:
            domain.append(('contract_id', '=', self.selected_contract_id.id))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending IPCs',
            'res_model': 'construction.ipc',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_open_pending_variations(self):
        domain = [('state', 'in', ['draft', 'submitted'])]
        if self.selected_contract_id:
            domain.append(('contract_id', '=', self.selected_contract_id.id))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending Variations',
            'res_model': 'construction.variation',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_open_pending_advances(self):
        domain = [('state', '=', 'draft')]
        if self.selected_contract_id:
            domain.append(('contract_id', '=', self.selected_contract_id.id))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending Advances',
            'res_model': 'construction.advance',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_open_pending_retention_releases(self):
        domain = [('state', '=', 'draft')]
        if self.selected_contract_id:
            domain.append(('contract_id', '=', self.selected_contract_id.id))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending Retention Releases',
            'res_model': 'construction.retention.release',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_new_contract(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Contract',
            'res_model': 'construction.contract',
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_new_ipc(self):
        context = {'form_view_initial_mode': 'edit'}
        if self.selected_contract_id:
            context['default_contract_id'] = self.selected_contract_id.id

        return {
            'type': 'ir.actions.act_window',
            'name': 'New IPC',
            'res_model': 'construction.ipc',
            'view_mode': 'form',
            'target': 'current',
            'context': context,
        }

    def action_new_variation(self):
        context = {'form_view_initial_mode': 'edit'}
        if self.selected_contract_id:
            context['default_contract_id'] = self.selected_contract_id.id

        return {
            'type': 'ir.actions.act_window',
            'name': 'New Variation',
            'res_model': 'construction.variation',
            'view_mode': 'form',
            'target': 'current',
            'context': context,
        }

    def action_new_advance(self):
        context = {'form_view_initial_mode': 'edit'}
        if self.selected_contract_id:
            context['default_contract_id'] = self.selected_contract_id.id

        return {
            'type': 'ir.actions.act_window',
            'name': 'New Advance',
            'res_model': 'construction.advance',
            'view_mode': 'form',
            'target': 'current',
            'context': context,
        }

    def action_new_retention_release(self):
        context = {'form_view_initial_mode': 'edit'}
        if self.selected_contract_id:
            context['default_contract_id'] = self.selected_contract_id.id

        return {
            'type': 'ir.actions.act_window',
            'name': 'New Retention Release',
            'res_model': 'construction.retention.release',
            'view_mode': 'form',
            'target': 'current',
            'context': context,
        }