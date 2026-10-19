# ABSAR Employee Portal Accounting — 18.0.1.0.2

An additional module for Odoo 18, Employee Portal Suite and the existing
`internal_transfer_voucher` module (source integration tested against
18.0.2.52.0). It does not replace or modify those module folders.

## Included

- Vendor bills and vendor credit notes: drafts, purchase-order billable-line
  import, expense accounts, units, discounts, taxes, analytic distributions,
  currencies, bill/accounting dates, references, recipient bank, payment terms,
  sections/notes, native totals preview and saved journal items.
- Miscellaneous journal entries: debit/credit balancing, line partners, due
  dates, foreign amounts, tax grids and analytic distributions.
- Payment and receipt vouchers: existing accounting posting, matching,
  reconciliation/unreconciliation, payment methods, journal-transfer
  destinations, PO allocations, bank fees and supporting documents.
- Planned payments/receipts: preparation, bulk outgoing submission to CEO,
  existing CEO approve/adjust/hold/reject logic, addition to existing weekly
  plans and creation of the draft accounting voucher at the existing handoff.
- Shared lists, search, company switching, forms, attachment upload/download,
  PDF printing, cancellation of editable drafts and native reset-to-draft checks.
- Sales invoice **creation and editing are excluded**. Receipt matching can
  select existing posted customer invoices belonging to the selected partner.

## Install and configure on staging

1. Add the `absar_portal_accounting` folder to the same custom-addons path as
   Employee Portal Suite and Payment & Receipt Voucher. Restart the build.
2. Update the Apps List, remove the Apps-only filter, search for
   **ABSAR Employee Portal Accounting**, and install it.
3. Under **Accounting → Configuration → Settings → Employee Portal Accounting**,
   select the company and the journals that this workspace may use. Save settings.
   Existing journal selections are preserved when upgrading. No journals are enabled automatically. Include the relevant purchase,
   miscellaneous, bank/cash and journal-transfer destination journals.
4. Keep **Review Internal Submissions Too** enabled to send manual native
   bills, miscellaneous entries and vouchers in these journals through the
   same review. Their first posting request submits them and leaves them in
   Draft. Native forms show Submit for Approval. Automatic bank-payment,
   statement and stock entries are excluded from this manual review hook.
5. On each intended user, assign the appropriate **Portal Accounting** role:
   **Accounting Preparer**, **Accounting Approver** or **Accounting Monitor**.
   Roles apply to internal and employee-linked portal accounts. Assign roles
   explicitly; installation does not enroll users or change account types.
6. Open the employee portal's **Accounting Workspace** link, or
   `/my/employee/accounting`.

| Role | Permission |
| --- | --- |
| Preparer | Create/edit own or unclaimed drafts, attach evidence, submit, cancel own editable drafts, prepare planned movements and create vouchers at the existing handoff |
| Approver | Read, independently approve/post, return with a reason, reconcile vouchers and request native reset-to-draft |
| Monitor | Read lists, forms and documents within company/journal scope |

CEO cash-planning decisions still require the **existing EPS CEO role**, in
addition to access to this workspace. Assigning Accounting Approver does not
grant CEO or payment-execution authority. Existing treasury bridge pages
continue to work.

The existing **internal Payment Execution Managers** retain Mark as Paid and
execution/reset approvals. Portal preparers do not receive that internal group.
Native voucher users still need the existing voucher/planning permissions;
this module does not repair or broaden their original ACLs.

## Review and accounting protections

- The preparer cannot approve their own document, including when holding both
  roles. Submitted documents are locked in the portal until returned.
- Native changes to a submitted bill/entry/voucher or its lines invalidate the
  review. Portal-origin documents cannot post through the native posting chain
  while unapproved. Existing records are not posted or migrated on installation.
- Company, journal, partner, account, PO, tax and analytic relations are checked
  before privileged operations. Portal groups do not imply internal/accounting
  groups and receive no generic accounting model ACLs.
- Row locks and record versions reject stale actions. Controller savepoints
  roll back failed saves, postings and bulk submissions together.
- Native accounting methods retain lock-date, balance, tax, reconciliation and
  custom voucher checks, including mandatory analytic distributions. Native
  abnormal amount/date warnings require explicit portal acknowledgment.
  Duplicate vendor references are checked across the
  company with normalized reference matching and a transaction lock.
- PO overpayment uses the existing voucher confirmation wizard. Posting first
  shows its details; the approver must explicitly confirm the overpayment.

## Limits of this first accounting release

- Your voucher engine posts amounts in company currency, so portal vouchers
  require company currency. Vendor bills use native currency handling.
- Weekly-plan creation/maintenance, execution, cash forecasting, Payment
  Reviews, bank statement reconciliation, assets, payroll, full accounting
  reports and signing workflows remain in their existing applications.
- Planned-payment reset approval stays with the existing internal workflow.
  Portal preparers can request that reset; an internal execution manager must
  approve it before editing becomes available again.
  Financial posting is not a bank transfer and does not execute a payment.
- No internal-user license conclusion follows from these technical access
  controls; commercial licensing remains governed by your Odoo agreement.

## Validation

The staging backend was inspected without saving/posting live records. The
actual new module installs/upgrades in a disposable Odoo 18 database alongside
the **full original voucher source**. A minimal EPS fixture replaces only the
Enterprise-dependent outer portal module in that local test environment.

Real ORM tests cover bills/credits/VAT, preview rollback, PO linking, balanced
entries, vouchers, reconciliation/unreconciliation, unplanned actuals, journal
transfers, CEO planning/adjustments, internal execution handoff, internal and
portal submission to shared approval, native resets, duplicate references,
company/journal boundaries, no sales-invoice creation and no portal conversion.
Actual QWeb forms/list/report rendering and frontend DOM fixtures are checked.

This design update has **not been deployed to staging yet**. The full live Employee
Portal Suite, Enterprise/localization, custom Studio and signing combination
must be smoke-tested there before production. PDF report HTML is validated;
the staging PDF renderer and final browser layouts still need that check.

## 18.0.1.0.2 design update

- Four workspace cards per desktop row, two on smaller screens and one on
  mobile, with subtle entrance/hover motion and reduced-motion support.
- Contained list scrolling, stable date/amount columns, grouped bulk controls
  and readable document names.
- Purchase-style accounting lines: core values in the main row, account and
  analytic details below; journal lines retain foreign amount, due date and
  tax-grid controls below their main row. Save payloads are preserved.
- Journal selection and internal review settings now live under Accounting →
  Configuration → Settings → Employee Portal Accounting. They still persist
  on the company; existing selections are retained. The previous company tab
  is inactive.
- This update adds no workflow or role changes. Keep your Employee Portal
  Suite unchanged. Accounting uses section elements inside the existing EPS
  layout, so the global EPS main spacing applies only once. The bundle also
  includes Purchase Workspace 18.0.1.5.10 (boxed upper PO fields only).
- Additional local upgrade/QWeb tests cover the settings move, company
  isolation, existing values, all seven cards, the bulk list and empty list.
  Frontend checks exercise saving rearranged journal details. Full live
  Enterprise layout verification remains after staging deployment.
