from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CashPlanAddToRunWizard(models.TransientModel):
    _name = 'cash.plan.add.to.run.wizard'
    _description = 'Add Planned Payment to Weekly Plan'

    line_id = fields.Many2one('cash.plan.line', required=True, readonly=True)
    company_id = fields.Many2one(related='line_id.company_id', readonly=True)
    run_id = fields.Many2one(
        'cash.plan.run', string='Weekly Plan', required=True,
        domain="[('company_id', '=', company_id), ('state', 'not in', ('done', 'cancel'))]",
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        line = self.env['cash.plan.line'].browse(vals.get('line_id') or self.env.context.get('default_line_id')).exists()
        if line and 'run_id' in fields_list:
            today = fields.Date.context_today(self)
            run = self.env['cash.plan.run'].search([
                ('company_id', '=', line.company_id.id),
                ('date_from', '<=', today),
                ('date_to', '>=', today),
                ('state', 'not in', ('done', 'cancel')),
            ], order='date_from desc, id desc', limit=1)
            if run:
                vals['run_id'] = run.id
        return vals

    def action_confirm(self):
        self.ensure_one()
        if not self.line_id:
            raise UserError(_('The planned payment no longer exists.'))
        self.line_id._assign_to_weekly_plan(self.run_id, self.env.user)
        return {'type': 'ir.actions.act_window_close'}
