# Existing EPS Bridge v0.9.8 - saved proposal HTTP 500 hotfix

## Error addressed
The supplied server traceback identifies:
- Route: `/my/workspace/sales/513`
- Template: `portal_backend_workspace.sales__document_detail_extra`
- Error: `ValueError: incomplete format`
- Runtime expression: `'%.2f%' % sum(order.absar_proposal_payment_ids.mapped('percentage'))`

The inherited markup is actually supplied by the existing bridge's
`views/proposals.xml`, template `proposal_document_detail`.
The previous ZIP contains `'%.2f%%'`, whereas the user's loaded template contains
`'%.2f%'`. This patch avoids that escaping boundary rather than adding another `%`.
The precise live import/translation path was not inspected.

## Fix
Only the numeric value is formatted. The percent sign is ordinary template text:

```xml
<strong t-translation="off"><t t-out="'{:.2f}'.format(sum(order.absar_proposal_payment_ids.mapped('percentage')))"/>%</strong>
```

An empty milestone collection displays `0.00%`; complete milestones display
`100.00%`; incomplete or overallocated drafts display their actual total.
The existing 100% pre-print validation is NOT changed or bypassed.
No numeric records or existing milestone data are modified by this patch.

## Exact package scope
- Same addon: `portal_backend_workspace_eps_bridge`.
- Bridge version: `18.0.0.9.8`.
- Main addon stays at `18.0.0.9.7`; 217 files verified byte-identical.
- Only changed runtime files: `__manifest__.py`, `views/proposals.xml`.
- 14 other bridge runtime files verified byte-identical.
- No new dependency, addon, schema field, migration, permission or data operation.
- Existing Customer / Client mapping, project integration, proposal editors,
  notification bell, routing, report actions and styles remain unchanged.

## Executed tests
- 12 strict expression/markup regression tests passed.
- 37 retained v0.9.7 customer/proposal fixture tests passed without modification.
- 31 XML and 55 Python files parsed across both supplied addons.
- Declared data-file presence checked.
- Original bridge runtime files compared byte-for-byte; source ZIPs preserved.
- The regression test deliberately reproduces the exact reported exception using
  the runtime expression. It also simulates `%%` -> `%` normalization at the XML
  boundary and verifies the repaired markup works before and after that step.
- Cases include no milestones, zero, a fractional total, complete 100%, incomplete
  99.99%, and an overallocated 110%. No fallback hides formatting errors.

These are local Python/XML/controlled-ORM fixture checks, NOT live Odoo tests.
No live Odoo registry, XML import, module upgrade, real session, proposal PDF, or
notification transport was run. Previous full-workspace limitations still apply.
The historical logs shipped with earlier versions are not presented as rerun tests.

## Upgrade
Replace the existing `portal_backend_workspace_eps_bridge` directory with this
complete directory, deploy/rebuild, and upgrade that SAME addon in Apps. Keep the
main `portal_backend_workspace` v0.9.7. Confirm the bridge version is 18.0.0.9.8,
then reopen the affected saved quotation. Do not uninstall either module.
A browser refresh alone will not load changed XML from the deployed source.

## Python formatting reference
Python's official string-formatting reference distinguishes the numeric formatting
conversion from a literal percent sign:
https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting
