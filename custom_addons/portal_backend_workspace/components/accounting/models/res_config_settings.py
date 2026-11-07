from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    portal_accounting_journal_ids = fields.Many2many(
        related="company_id.portal_accounting_journal_ids", readonly=False,
        groups="base.group_system",
    )
    portal_accounting_review_internal = fields.Boolean(
        related="company_id.portal_accounting_review_internal", readonly=False,
        groups="base.group_system",
    )
