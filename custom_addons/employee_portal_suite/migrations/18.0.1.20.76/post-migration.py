# -*- coding: utf-8 -*-
"""Repair portal group conversations without deleting any conversation."""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Portal groups are messaging conversations, not /meet-style rooms.  Odoo's
    # meeting display mode causes the public Discuss page to show camera preview
    # immediately on open.  Clear it on all existing portal groups.
    groups = env['discuss.channel'].sudo().search([
        ('channel_type', '=', 'group'),
        ('is_employee_portal_channel', '=', True),
    ])
    if groups:
        groups.write({'default_display_mode': False})

    # 20.75 accidentally deleted the exact legacy #Company channel in a test DB.
    # The legacy wrapper uses ondelete='set null', so if that wrapper still exists
    # we can recreate its canonical Discuss channel with the original participants.
    # This is deliberately limited to that one name and only when the link is gone.
    threads = env['portal.chat.thread'].sudo().search([
        ('is_group', '=', True),
        ('name', '=', '#Company'),
        ('discuss_channel_id', '=', False),
    ])
    for thread in threads:
        try:
            channel = thread._ensure_discuss_channel()
            if channel:
                channel.write({'default_display_mode': False})
        except Exception:
            # Do not block the module upgrade if this legacy wrapper cannot be
            # reconstructed; no other conversation should be touched.
            continue
