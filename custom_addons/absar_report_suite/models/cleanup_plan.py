"""Pure graph rules: only allowlisted custom records with no retained consumers."""
ALLOWED_OWNERS = frozenset({'studio_customization', 'absar_report_suite', '__export__',
                          '__custom__', 'wm_journal_entry_report'})


def plan_cleanup(candidates, owners, protected, references):
    """References are (consumer, target); None consumers are external roots.

    Nodes are (model, id). Every unknown ownership or retained dependency keeps
    a record. Fixed-point propagation also preserves its transitive dependencies.
    """
    removable = set(candidates) - set(protected)
    reasons = {node: 'retained report or system record' for node in set(candidates) & set(protected)}
    for node in list(removable):
        if set(owners.get(node, ())) - ALLOWED_OWNERS:
            removable.remove(node)
            reasons[node] = 'external ID belongs to a protected addon'
    changed = True
    while changed:
        changed = False
        for consumer, target in references:
            if target in removable and consumer not in removable:
                removable.remove(target)
                reasons[target] = 'referenced by a retained record'
                changed = True
    return removable, reasons
