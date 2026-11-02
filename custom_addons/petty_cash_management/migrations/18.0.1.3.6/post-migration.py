from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Remove legacy access/rules before deleting the obsolete group so rules
    # cannot become global through an empty group relation.
    for name in (
        'petty_cash_portal_approver_rule', 'petty_cash_line_portal_approver_rule',
        'access_petty_cash_portal_approver', 'access_petty_cash_line_portal_approver',
        'access_petty_cash_category_portal_approver', 'group_portal_petty_cash_approver',
    ):
        record = env.ref('petty_cash_management.' + name, raise_if_not_found=False)
        if record:
            record.unlink()
