# Petty Cash Management — Recording Demo

Full Odoo 18 module, version 18.0.1.3.11. Optional Employee Portal Bridge version 18.0.1.3.4 adds portal recording examples to the same setup. No sample records are created during installation or upgrade.

## Start

1. Install/upgrade **Petty Cash Management** first.
2. For portal recording, ensure Employee Portal Suite is installed, then install/upgrade **Petty Cash Management - Employee Portal Bridge**.
3. Sign in as an Accounting Administrator and select the company to populate.
4. Open **Petty Cash → Recording Demo Setup → New**.
5. Choose the backend recording account and the existing accounting reviewer, supervisor and final approver accounts. The same internal account may be used for all three roles for a single-session backend demonstration.
6. With the bridge installed, leave **Include portal employee examples** enabled and select the existing Employee Portal user you will use for filming.
7. Leave **Enable petty cash roles for selected recording accounts** checked to grant the relevant petty cash groups. This grants only the selected petty cash roles; it does not convert Portal users to Internal users or create users/employees. If you uncheck it, configure the existing role memberships separately before testing workflow actions.
8. Tick **This is a development/demo database**, save and click **Create Recording Examples**.

Use a development/demo database only. The optional posted examples affect accounting reports. Uncheck **Include posted accounting examples** if you want both generated vouchers per owner to remain draft. All fixtures and role preparation are created within one savepoint, so a failed build rolls back its database changes. A second click on a Ready setup opens the existing examples; it does not duplicate them. There is no automatic deletion/reset of posted samples.

## Data created

With both modules and portal examples enabled:

- 24 petty cash reports: 12 backend-owned and 12 portal-owned.
- 72 expense lines, including consumables, fuel/transport, stationery, repairs/tools, welfare and personal-expense rejection examples.
- 70 clearly marked fictional PDF receipts linked to expense lines and reports. The missing-fuel-receipt report intentionally has one receipt missing. Receipt copies on accounting entries are additional.
- Mixed VAT/no-VAT reports; a dedicated illustrative 15% purchase tax and input VAT account.
- Six expense categories mapped to dedicated sample expense accounts, and two analytic project accounts.
- Supplier, receipt/invoice, PO/MR and project/zone references.
- Per owner: two ordinary drafts, two returned drafts, three reports awaiting different review stages, one rejected report and four approved reports.
- Two generated accounting entries per owner: one draft and, if enabled, one posted. These examples use no-VAT lines; VAT examples remain as reports for review and demonstration.

Backend only creates half those counts: 12 reports, 36 lines, 35 receipt PDFs and two entries.

The scenario list per owner is:

1. Draft ready to submit.
2. Draft with mixed taxable and non-taxable lines.
3. Awaiting accounting review.
4. Awaiting supervisor review.
5. Awaiting final approval.
6. Returned for a missing fuel receipt.
7. Returned for category/reference correction, with first review history.
8. Rejected personal expenses.
9. Approved VAT report awaiting accounting.
10. Approved no-VAT report ready to create its voucher.
11. Approved report with linked draft journal entry.
12. Approved report with linked posted entry, or another draft if posting was disabled.

## Portal recording

Sign in as the **selected portal account** in a separate browser profile/private window. Open `/my/employee/petty-cash` or use Employee Portal → Reports → Petty Cash. It will show that user's own 12 sample reports, including draft and returned reports that can be edited/resubmitted. The portal list does not show another employee's reports.

The selected portal account receives Portal Petty Cash User access when role preparation is enabled. Existing per-user accounting mappings are kept; a mapping is created only if missing. Dedicated demo accounts/journal are set explicitly on sample reports. New manually-created portal reports continue to use the user's configured mapping.

Reviewers can use `/my/employee/petty-cash/approvals` when their existing login has the required role. You may select existing portal users as reviewers; assigning the plain review role does not make them internal users. Use separate recordings/logins if you want to demonstrate three different approvers. No credentials are embedded and no new users are created.

## Filming order

Portal My Petty Cash Reports → draft report/expense detail → receipt attachment → submit → accounting review → supervisor review → final approval → returned/rejected example → approved report → Create Voucher → linked draft entry/attachments → posted example → backend filters, categories and analytic mapping → PDF printout.

Use **Open Sample Reports** on the setup for a list showing each report's recording scenario. Normal reports lists/dashboard counters also include these examples. Demo references start with `DEMO /`. Review history is explicitly fictional and seeded without sending approval notifications; workflow actions performed during filming use the module's normal checks and notifications.

## Boundaries and validation

The existing petty cash workflow, tax calculation, accounting generation and portal routes have not been replaced. Demo generation uses its own private fixture builder and the existing private workflow-write token for sample histories; public workflow protections remain unchanged.

Python syntax, module manifest paths, XML parsing, the PDF receipt parser check and the focused offline checks passed. Transactional Odoo tests are included for creation counts, totals, accounting balance, copied attachments, idempotency, administrator opt-in, rollback, portal ownership and Portal/Internal user-type preservation. An Odoo runtime/database is unavailable in this build environment; installation/integration tests have not been executed here. Additional company localization or other custom modules may impose their own validations.

On a disposable Odoo 18 test database, run:

`--test-enable --test-tags /petty_cash_management:TestPettyCashRecordingDemo,/petty_cash_management_portal_bridge:TestPettyCashPortalRecordingDemo -u petty_cash_management,petty_cash_management_portal_bridge --stop-after-init`

Keep the technical folder names `petty_cash_management` and `petty_cash_management_portal_bridge` unchanged.
