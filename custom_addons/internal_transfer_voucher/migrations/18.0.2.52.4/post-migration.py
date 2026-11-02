from odoo import api, SUPERUSER_ID
from odoo.tools.safe_eval import safe_eval


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    favorites = env['ir.filters'].search([('model_id', 'in', ['account.payment.voucher', 'account.receipt.voucher', 'cash.plan.line']), ('is_default', '=', True)])
    for favorite in favorites:
        try:
            context = safe_eval(favorite.context or '{}', {'uid': favorite.user_id.id or SUPERUSER_ID})
        except (ValueError, TypeError, NameError, SyntaxError):
            continue
        if isinstance(context, dict) and context.get('group_by'):
            favorite.write({'is_default': False})
