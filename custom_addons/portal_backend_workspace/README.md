# Portal Backend Workspace - 18.0.0.9.2

Independent Odoo 18 addon containing the migrated Sales, Purchase,
Accounting and HR Administration workspaces. This release replaces the simplified
v0.8 pages; it is not an installer for the original four addons.

## This update - original layout contract restored

This updates the existing consolidated addon; it does not replace the four
original workspace editors with generic Odoo tables or forms.

- Restore the original EPS `#wrap.container.mt-3.mb-5` shell. The former
  `container-fluid px-3 px-md-4 py-3` wrapper prevented original full-width
  selectors from matching and introduced a second set of gutters.
- Restore the original 80% desktop density starting at 769px, applied in the
  page head before paint; mobile remains unscaled and print uses 100%.
- Restore the original DM Sans weight/italic font request.
- Load the exported compact-list helper as an ES module instead of a classic
  script, fixing its browser syntax error. Version all direct shell assets.
- Restore the visible standard Document Type field on New Quotation; no
  technical-proposal addon or nonfunctional technical option is introduced.
- Retain the migrated Sales/Purchase/Accounting/HR forms, grids, tabs, filters,
  role checks and workflow logic from 0.9.1. No new custom dependency or routing
  change. The existing EPS navigation bridge does not need changing.

Read `LAYOUT_VALIDATION.md` and `TEST_REPORT.md` for exact executed checks,
source comparisons and limits. Live Odoo execution has not been verified here.

## Source baseline

| Workspace | Source version |
| --- | --- |
| Sales | 18.0.1.4.14 |
| Purchase | 18.0.1.7.4 |
| Accounting | 18.0.1.3.9 |
| HR Administration | 18.0.1.0.17 |
| Extracted EPS portal styling/navigation reference | 18.0.1.20.125 |

Original business templates, frontend editors, controllers and workflow logic
were migrated into component folders inside this single addon. XML identifiers,
asset paths, role groups, model extensions and URLs were namespaced for PBW.
Employee Portal Suite business models are not bundled.

## Requirements

Odoo 18, with its standard Sales, Purchase/Inventory, Accounting, Projects,
Employees, Attendance, Contracts, Work Entries and Payroll applications. Native
`hr_payroll` is required for the payroll workspace; this is an Enterprise-dependent
build, not a Community-only payroll replacement. Odoo installs declared standard
dependencies normally.

There is NO required third-party/custom addon: Employee Portal Suite,
Customer/Vendor Portal, Internal Transfer Voucher, Construction Contract Management,
Technical Proposal, custom printing and the previous four portal addons are NOT
required by the base addon.

## Install or upgrade in Dev

1. Replace the ENTIRE `portal_backend_workspace` directory in your addons
   repository with the folder in this ZIP. Do not overlay old failed builds;
   obsolete Python files must not remain in the module directory.
2. Deploy/restart the Dev build, update the Apps list, and install or upgrade
   **Portal Backend Workspace**. Upgrade the same technical addon name.
3. Hard-refresh the browser after the module upgrade to load the new assets.
4. Link a portal test account under Employees > Settings > Related User. The
   selector permits active, company-compatible portal accounts without granting
   internal-user permissions.
5. Assign the relevant workspace roles on the user. Each role implies Workspace
   Access. Configure authorized companies; do not give every test user every role.
6. For Accounting, select allowed journals in Accounting > Configuration >
   Settings > Workspace Accounting > Portal Journals for each company. Empty
   selections intentionally deny accounting operations. Include sales journals
   for customer invoices, purchase journals for bills, and general journals for
   journal entries. Save settings before opening the accounting workspace.
7. Configure native payroll structures, employee contracts and work entries before
   testing payroll. The Employee/Attendance role does not include payroll access.
8. Log in as the portal account and open `/my/workspace`.

The previous Dev group XML IDs are retained as compatibility groups. Sales and
Purchase legacy access imply all-company workspace roles; legacy Accounting
access implies restricted preparation plus customer invoicing; legacy HR access
implies Employee/Attendance administration only. Review roles after upgrading;
Direct Posting, Approver and Payroll remain separately assigned permissions.

## Retained workspace functionality

- Sales: original compact lists, search/filter/status displays, quotation header
  and product-line editors, product catalog/create/edit, analytics, native price
  and tax previews, keyboard entry, sections/notes/reordering, save-on-leave,
  quotation approval and subsequent sales-order approval, return for correction,
  scoped printing and review updates.
- Purchase: original lists, order forms, product editor/catalog, analytics,
  native totals, issuer/approver/monitor/all-company roles, independent approval,
  return for correction, partial receipt workflow, document attachments and
  native PO-to-bill integration with the Accounting workspace.
- Accounting: original invoice/bill and journal editors, native product/tax/
  analytic controls, permitted-journal boundaries, direct-posting or restricted
  preparation/independent approval, reset-to-draft requests, audit/history,
  native invoice printing, standalone journal report, standard PO billing and
  sales-order invoicing.
- HR: original employee, attendance, contract, work-entry, payslip and payroll
  batch screens, attendance timesheet, scoped native report printing and separate
  employee/attendance versus payroll administration roles.
- Foundation: extracted EPS desktop/mobile stylesheet and navigation patterns,
  desktop sidebar, mobile drawer and create menu, independent notification bell,
  per-workspace permissions, and company-scoped access checks.

## Deliberately not in the base addon

Material/Employee Requests and MR/ER Admin Control, vendor-submission review,
custom payment/receipt vouchers and payment plans, construction IPCs, technical
proposals, EPS salary estimators, custom direct printing and proprietary signing
integrations require separate bridges. Their controls and hard references were
removed from this base. Native invoices, bills, journal entries and receipts
remain; missing custom features are not replaced with fake generic screens.

## Employee Portal Suite coexistence

Base URLs and assets use PBW-specific namespaces. The base does not import EPS,
change `/my/employee`, or grant EPS roles. Explicit deep links are preserved.

The separately supplied `portal_backend_workspace_eps_bridge` coordinates
navigation and login landing when BOTH products are installed: employee-linked
portal users keep the EPS default `/my/employee`; authorized users can still
open `/my/workspace` and see cross-product links. Install the optional bridge
only with both products; it is NOT required for this addon to operate alone.

That bridge is navigation/routing only. MR/ER transaction integrations are not
implemented by that bridge.

## Validation status

See TEST_REPORT.md and PARITY_AUDIT.md. This is a targeted source-parity repair of
v0.9, not a certification that the four original addons are fully reproduced.
21 targeted regression checks pass; 16 of 28 adapted original fixture scripts pass.
The other 12 harness executions are recorded and explained, not counted as passes.
Isolated desktop/mobile Accounting dialog styles match the original in Chromium.
Live Odoo installation, native transaction engines and full screen/workflow parity
remain unverified. Original custom integrations remain excluded as documented.
