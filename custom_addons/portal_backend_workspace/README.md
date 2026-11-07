# Portal Backend Workspace 18.0.0.8.0

Standalone Odoo 18 dev build. **No dependencies on Employee Portal Suite, Customer/Vendor Portal, Internal Transfer Voucher, Construction Management, Technical Proposal, or any other custom module.**

Requires only standard Odoo apps: base, web, portal, website, mail, sale_management, purchase, account, hr, hr_attendance, hr_contract. `hr_contract` and some others may depend on the edition/app availability. Install these official apps as required.

## Current working scope
- EPS-inspired independent layout and four workspace cards.
- Per-workspace portal groups and company-scoped lists and details for standard Odoo Sales Orders, Purchase Orders, Customer Invoices/Vendor Bills and Employees.
- Simple draft creation for those four standard models.
- Employee `Related User` field adjustment for choosing existing portal accounts.
- Explicit URL `/my/workspace`. Does **not override `/my`, `/my/employee`, or login redirect**, to avoid collisions with EPS; a future optional integration bridge can connect navigation and default routing.

## Not yet included
- Full original proprietary Sales/Purchase/Accounting/HR advanced UI, approval engine, lines editors, notifications, payroll and voucher actions. The previous combined v0.7 source contained mandatory custom dependencies and is NOT reused.
- MR/ER, technical proposals, project-costing, specialized voucher operations, and customer/vendor integrations: these must remain in separately installable bridges.

## Dev install
Put the single `portal_backend_workspace` folder into a custom addons path. Refresh Apps. Upgrade/install Portal Backend Workspace. Grant group `Workspace Access` and appropriate Sales/Purchase/Accounting/HR Workspace to portal accounts. Browse `/my/workspace`.

## Security
The implementation uses explicitly scoped `sudo()` operations guarded by workspace groups and current company. It is for **development testing**, not a security-certified production addon; review record-level access and privacy before deployment. Do not assign sensitive Accounting or HR groups to untrusted accounts.
