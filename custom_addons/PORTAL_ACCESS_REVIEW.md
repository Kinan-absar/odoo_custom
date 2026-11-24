# ABSAR Odoo 18 portal access review

Reviewed the 23 modules in Archive(20261120-185924).zip. The release contains all 23 modules and updates 16 of them. The versions below refer to this archive.

## Published Odoo rules

Odoo's published Enterprise agreement excludes accounts used by external people or systems with limited access through the portal. The currently published agreement and pricing page also define Light Users. I found no public Odoo 18 group allowlist that makes employee use of internal business workflows eligible for the external portal exclusion. The release uses Odoo 18's native internal-user check and leaves subscription accounting to Odoo. The source archive cannot establish the terms applicable to ABSAR's existing agreement, the headcount behind the 55-seat quote, or what Odoo will invoice.

- [Odoo 18 Enterprise Subscription Agreement](https://www.odoo.com/documentation/18.0/legal/terms/enterprise.html)
- [Odoo 18 portal access documentation](https://www.odoo.com/documentation/18.0/applications/general/users/portal.html)
- [Odoo pricing and Light User definition](https://www.odoo.com/pricing)
- [Odoo 18 source for request authentication](https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/models/ir_http.py)

## Module changes

| Module | Release | Portal access finding and change |
|---|---|---|
| absar_direct_print | 18.0.1.0.11 | Removed the Print User role's implication of the native Internal User role and its automatic admin membership on fresh installs. Printing now requires both internal status and the appropriate print role. Paired print agents still authenticate with their station token. |
| absar_payment_voucher_sign | 18.0.1.0.3 | Voucher signature preparation uses voucher permissions. It relies on the hardened voucher module, and native Sign invitations can still go to external recipients. |
| absar_payroll_employee_accrual | 18.0.1.1.13 | Uses the native payroll posting flow. No source change needed for portal access. |
| absar_payroll_transfer_bridge | 18.0.1.0.2 | Extends the voucher posting flow for payroll. It relies on the hardened voucher module. |
| absar_portal_accounting | 18.0.1.2.16 | Blocked portal access to the custom accounting workspace and posting wizard. |
| absar_portal_purchase_monitor | 18.0.1.6.18 | Restricted purchasing workspace routes to internal accounts and limited the ungrouped bill ACL to Accounting users. |
| absar_portal_sales | 18.0.1.4.15 | Restricted custom quotation and sales workflows to internal accounts. External customer access uses customer-facing documents. |
| absar_portal_sales_bell_bridge | 18.0.1.0.2 | Restricted sales notifications and their routes and records to internal accounts. |
| absar_premium_backend | 18.0.5.4.1 | Restricted backend theme requests to internal users and configuration updates to Settings administrators. |
| absar_report_suite | 18.0.2.0.34 | Report bindings and configuration use native business models and Settings access. No source change needed for portal access. |
| absar_send_to_sign_po | 18.0.1.1.16 | Restricted preparation and tracking of purchase-order signatures to internal users. Native Sign access for invited recipients remains available. |
| absar_sign_workflow_core | 18.0.1.0.16 | No source change needed on the core. Business-document preparation is gated in the source modules. Standard external signing remains available. |
| absar_technical_proposal | 18.0.1.1.8 | Proposal creation and editing use Sales permissions. No source change needed for portal access. |
| account_statement_reports | 18.0.20.1.6 | Accounting groups already protect the workbench and its models. The external customer controller no longer serves statement workbench data. |
| construction_contract_management | 18.0.1.8.24 | Revoked grants from the construction portal role and restricted construction records to internal accounts. |
| construction_contract_management_portal_bridge | 18.0.1.2.2 | Restricted the contract, progress certificate and variation workspace routes to internal accounts. |
| construction_contract_sign_bridge | 18.0.1.1.4 | Restricted preparation to internal users who can write the source document, and status access to those who can read it. |
| customer_vendor_portal | 2.0.1 | Retained partner-scoped document viewing. Customers see their posted invoices and customer-facing sales records. Vendors see their confirmed POs and existing invoice statuses. Removed the custom invoice upload and statement workbench access. Internal reviewers can still manage vendor invoice records. |
| employee_portal_suite | 18.0.1.20.134 | Restricted the employee workspace, attendance, requests and approvals, salary reports, document handling, chat and notifications to internal accounts. Removed portal-specific native HR and Discuss grants and restricted approval assignment to active internal users. |
| eps_itv_treasury_bridge | 18.0.1.5.2 | Restricted treasury routes and actions through the employee workspace to internal accounts. |
| internal_transfer_voucher | 18.0.2.52.6 | Restricted the ungrouped payment voucher ACL to Accounting users. |
| petty_cash_management | 18.0.1.3.11 | Revoked the legacy portal role's report and line ACLs. Added internal-only record rules. |
| petty_cash_management_portal_bridge | 18.0.1.3.4 | Restricted petty cash report submission, viewing and review routes to internal accounts. |

## Upgrading an existing database

Upgrade the installed modules from the changed-module list together on a staging copy. Replacing files and restarting does not apply updated access records or run the Employee Portal Suite migration.

The Employee Portal Suite migration removes obsolete baseline groups from employee-linked portal accounts. It removes prior memberships for those users in channels marked by the suite and revokes public flags and links on employee and material request attachments. Employee records, user types, and transaction history are retained. Review pending steps assigned to portal employees and reassign them to eligible internal reviewers. The custom employee attendance app requires a connection to open protected pages. Its updated service worker removes previously cached employee pages when it activates in the browser.

A fresh Direct Print install requires assigning the appropriate print role to an existing internal account. Existing intentional print assignments can remain. Older standalone accounting and purchasing QA scripts in the archive contain fixtures based on the former portal capabilities and do not validate this release's access policy.

## Verification

Validated Python syntax in 279 files, parsed 218 XML files, checked each manifest's data files, checked 221 model-access rows, and verified 182 custom route declarations use the internal-account guard. Exercised the guard with anonymous, portal and internal test principals in an isolated mock. Added a Direct Print regression test for a portal account carrying the custom role. The archive was not installed or upgraded on an Odoo 18 Enterprise database here, so live behavior and the database migration remain unverified.

On staging, use an employee-linked portal account, an unrelated customer, a vendor, an authorized internal reviewer and an internal employee without the reviewer role. Verify that the portal employee cannot open or act on employee workflows, the reviewer can complete a request in an assigned role, the vendor and customer can only view their respective documents, and login in each account retains the expected native Odoo user role.
