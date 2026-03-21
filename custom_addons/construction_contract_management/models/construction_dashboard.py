from odoo import api, fields, models


class ConstructionDashboard(models.Model):
    _name = 'construction.dashboard'
    _description = 'Construction Dashboard'

    name = fields.Char(default='Dashboard', required=True)

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

    @api.depends_context('uid')
    def _compute_dashboard(self):
        Contract = self.env['construction.contract']
        IPC = self.env['construction.ipc']
        Variation = self.env['construction.variation']
        Advance = self.env['construction.advance']
        RetentionRelease = self.env['construction.retention.release']

        active_contracts = Contract.search([('state', '=', 'active')])
        all_contracts = Contract.search([])

        approved_ipcs = IPC.search([('state', 'in', ['approved', 'done'])])
        pending_ipcs = IPC.search([('state', 'in', ['draft', 'under_review'])])

        pending_variations = Variation.search([('state', 'in', ['draft', 'submitted'])])
        pending_advances = Advance.search([('state', '=', 'draft')])
        pending_retention_releases = RetentionRelease.search([('state', '=', 'draft')])

        for rec in self:
            rec.active_contract_count = len(active_contracts)
            rec.total_revised_amount = sum(all_contracts.mapped('revised_amount'))
            rec.total_certified_amount = sum(all_contracts.mapped('total_certified_amount'))
            rec.total_invoiced_amount = sum(all_contracts.mapped('total_move_amount'))
            rec.total_paid_amount = sum(all_contracts.mapped('total_paid_amount'))
            rec.total_advance_balance = sum(all_contracts.mapped('advance_balance'))
            rec.total_retention_balance = sum(all_contracts.mapped('retention_balance'))

            rec.pending_ipc_count = len(pending_ipcs)
            rec.pending_variation_count = len(pending_variations)
            rec.pending_advance_count = len(pending_advances)
            rec.pending_retention_release_count = len(pending_retention_releases)

    def action_open_contracts(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Contracts',
            'res_model': 'construction.contract',
            'view_mode': 'list,form',
        }

    def action_open_active_contracts(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Active Contracts',
            'res_model': 'construction.contract',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'active')],
        }

    def action_open_pending_ipcs(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending IPCs',
            'res_model': 'construction.ipc',
            'view_mode': 'list,form',
            'domain': [('state', 'in', ['draft', 'under_review'])],
        }

    def action_open_pending_variations(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending Variations',
            'res_model': 'construction.variation',
            'view_mode': 'list,form',
            'domain': [('state', 'in', ['draft', 'submitted'])],
        }

    def action_open_pending_advances(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending Advances',
            'res_model': 'construction.advance',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'draft')],
        }

    def action_open_pending_retention_releases(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending Retention Releases',
            'res_model': 'construction.retention.release',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'draft')],
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
        return {
            'type': 'ir.actions.act_window',
            'name': 'New IPC',
            'res_model': 'construction.ipc',
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_new_variation(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Variation',
            'res_model': 'construction.variation',
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_new_advance(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Advance',
            'res_model': 'construction.advance',
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_new_retention_release(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Retention Release',
            'res_model': 'construction.retention.release',
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }