from odoo import fields, models


class PaymentReviewWindowAction(models.Model):
    _inherit = 'ir.actions.act_window'

    cash_plan_review_id = fields.Many2one(
        'cash.plan.review', readonly=True, copy=False, index=True, ondelete='set null',
    )
    _sql_constraints = [
        ('cash_plan_review_action_unique', 'unique(cash_plan_review_id)',
         'Each Payment Review has one recommendations action.'),
    ]
