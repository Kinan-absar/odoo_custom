"""Keep existing internal purchasers able to issue through the shared queue."""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    issuer = env.ref('absar_portal_purchase_monitor.group_portal_purchase_preparer', raise_if_not_found=False)
    purchasers = env.ref('purchase.group_purchase_user', raise_if_not_found=False)
    if issuer and purchasers:
        issuer.write({'users': [(4, user.id) for user in purchasers.users if not user.share]})
