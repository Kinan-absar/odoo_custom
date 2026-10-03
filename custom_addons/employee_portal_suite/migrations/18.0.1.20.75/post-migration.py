# -*- coding: utf-8 -*-
"""One-time cleanup for the broken legacy #Company portal group conversation."""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Channel = env['discuss.channel'].sudo()

    # This exact legacy group is the broken conversation reported in the portal.
    # Restrict the cleanup to Employee Portal group conversations so normal Odoo
    # channels or unrelated records can never be touched.
    company_groups = Channel.search([
        ('channel_type', '=', 'group'),
        ('is_employee_portal_channel', '=', True),
        ('name', '=', '#Company'),
    ])
    if company_groups:
        company_groups.unlink()
