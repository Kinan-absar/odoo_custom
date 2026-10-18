"""Consolidate legacy roles without granting internal or native model access."""
from odoo import api, SUPERUSER_ID

PREFIX = 'absar_portal_purchase_monitor.'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    issuer = env.ref(PREFIX + 'group_portal_purchase_preparer', raise_if_not_found=False)
    approver = env.ref(PREFIX + 'group_portal_purchase_approver', raise_if_not_found=False)
    if not issuer or not approver:
        return
    # Preserve users who already held approval authority in version 1.5.4.
    managers = env.ref('purchase.group_purchase_manager', raise_if_not_found=False)
    if managers:
        approver.write({'users': [(4, user.id) for user in managers.users]})
    for old_name, target in [('confirmer', approver), ('product_creator', issuer)]:
        old = env.ref(PREFIX + 'group_portal_purchase_' + old_name, raise_if_not_found=False)
        if not old or old == target:
            continue
        target.write({'users': [(4, user.id) for user in old.users]})
        # Keep external identifiers as aliases, not additional group records.
        env['ir.model.data'].search([('module', '=', 'absar_portal_purchase_monitor'),
                                    ('model', '=', 'res.groups'), ('res_id', '=', old.id)]).write({'res_id': target.id})
        old.unlink()
    native = env.ref(PREFIX + 'group_portal_purchase_native', raise_if_not_found=False)
    if native:
        # Retired native hosting grants no replacement capability.
        native.unlink()
