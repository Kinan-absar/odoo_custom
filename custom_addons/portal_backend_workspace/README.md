# Portal Backend Workspace — Odoo 18 Dev prototype 0.4

Single installable module, four operational workspaces: Sales, Purchase, Accounting and HR.

## Included
- Dedicated dashboard and sections
- Group-scoped access, company-scoped list/detail pages
- Draft creation: Sales quotation, Purchase order, Vendor bill or customer invoice, Employee record
- Employee user linking enhancement
- EPS coexistence: for dual members EPS remains default, workspace remains at `/my/workspace`; switch link shown inside workspace
- No dependency on Employee Portal Suite, Customer/Vendor Portal, or older portal modules

## NOT included yet
Legacy workflows have **not** been merged feature-by-feature. No line editor, taxes, approval stages, purchasing receipts, HR attendance/payroll transaction workflows, signing, advanced accounting vouchers or notification engine. Do not represent as a functional replacement for published modules.

## Dev test
Update code, restart, upgrade module. Test with one workspace-only portal user and one user with both EPS and Workspace groups in a separate database copy with EPS installed. Verify default routes and explicit links. Verify each group can access only its permitted section.

## Licensing and security
Providing write operations to portal users may be subject to Odoo licensing. This Dev build uses elevated ORM operations guarded by workspace groups and company domains. Production security requires a full threat-model review, finer record rules, auditing, and proper permissions.
