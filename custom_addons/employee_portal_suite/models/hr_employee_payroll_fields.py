# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ── Overtime ──────────────────────────────────────────────────────────────
    # Disabled by default. Must be explicitly turned on per employee.
    eps_overtime_enabled = fields.Boolean(
        string='Overtime Enabled',
        default=False,
        help='When enabled, overtime hours are calculated and added to the salary. '
             'Disabled by default — turn on only for employees whose contracts allow OT.',
    )

    # ── Target hours override ─────────────────────────────────────────────────
    # Leave at 0 to use the working schedule hours automatically.
    eps_target_hours = fields.Float(
        string='Target Hours Override',
        default=0.0,
        help='Override the monthly target hours for this employee. '
             'Leave at 0 to use the hours calculated from the working schedule.',
    )
