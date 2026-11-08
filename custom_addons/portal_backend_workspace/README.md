# Portal Backend Workspace 18.0.0.9.7

## Current correction
Customer / Client is restored to the original stored `absar_is_sales_customer`
field, not a renamed separate PBW checkbox. Existing original values are preserved.
The versioned pre-upgrade migration seeds only PBW-only databases whose original
column did not exist; it does not overwrite existing original classifications.
The former workspace flag is retained as hidden historical data, not an OR fallback.

The existing EPS bridge v0.9.7 exposes the original proposal editor on new quotations
immediately after choosing Technical & Financial Proposal, with full draft content
saved together with the quotation. No additional bridge is needed. See
TEST_REPORT_v0.9.7.md for exact changed functions and test limits.

Upgrade this addon first, then the existing bridge, and refresh the portal.
Do not uninstall. A live registry/database upgrade was not run here.

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

## Optional integrations
The existing EPS bridge connects navigation, notification bell, the original Sales
customer checkbox, construction-project mapping and the original technical proposal
engine when present. It does not add MR/ER or custom-voucher workflows.
No Employee Portal Suite source is changed by these packages.

## Validation
See TEST_REPORT.md for executed checks and limits. This patch has local fixture,
DOM and syntax verification, not a live Odoo installation or full workflow-parity
certification. Historical reports in validation/ refer to earlier versions only.
