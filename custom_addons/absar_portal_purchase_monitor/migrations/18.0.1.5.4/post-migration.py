from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True, 'mail_notrack': True})
    orders = env['purchase.order'].search([
        ('absar_portal_preparer_id', '!=', False), ('user_id', '=', False)])
    for order in orders:
        preparer = order.absar_portal_preparer_id
        if order.company_id in preparer.company_ids:
            order.write({'user_id': preparer.id})
    legacy = env['purchase.order'].search([
        ('absar_portal_preparer_id', '!=', False), ('state', 'in', ['draft', 'sent']),
        ('absar_portal_review_state', '=', 'approved'),
        ('absar_portal_approver_id.share', '=', True)])
    legacy.write({'absar_portal_review_state': 'submitted',
                  'absar_portal_approver_id': False, 'absar_portal_approved_on': False})
