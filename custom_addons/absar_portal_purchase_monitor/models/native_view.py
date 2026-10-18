"""Adapt existing presentation groups on the resolved view architecture.

Do not inherit numbered group matches: supported Odoo 18 revisions and installed
extensions can contain different numbers of UoM/analytic controls. This helper
is called only for an opted-in portal identity before view postprocessing.
It changes display groups, never model ACLs or user group membership.
"""
from copy import deepcopy

NATIVE_GROUP = 'absar_portal_purchase_monitor.group_portal_purchase_native'
PRESENTATION_GROUPS = frozenset({
    'uom.group_uom', 'analytic.group_analytic_accounting',
    'base.group_multi_currency', 'base.group_multi_company',
})


def prepare_native_arch(arch, purchase=False):
    result = deepcopy(arch)
    for node in result.iter():
        groups = [part.strip() for part in (node.get('groups') or '').split(',') if part.strip()]
        if not groups:
            continue
        if '!uom.group_uom' in groups:
            # Hide the standard duplicate/fallback UoM from the opted-in portal.
            if '!' + NATIVE_GROUP not in groups:
                groups.append('!' + NATIVE_GROUP)
        elif (PRESENTATION_GROUPS.intersection(groups) or
                (purchase and node.tag == 'button' and
                 node.get('name') == 'print_quotation' and 'base.group_user' in groups)):
            if NATIVE_GROUP not in groups:
                groups.append(NATIVE_GROUP)
        node.set('groups', ','.join(groups))
    return result
