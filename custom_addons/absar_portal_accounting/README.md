# ABSAR Employee Portal Accounting — 18.0.1.1.0

Employee accounting for Odoo 18 with the existing Employee Portal Suite and
Payment & Receipt Voucher module. Employee Portal Suite is unchanged.

## Choose how each person works

| Person / role | Behavior |
| --- | --- |
| Regular portal accountant: Accounting User (Direct Posting) | Create and save drafts, post bills/credits/miscellaneous entries/payment and receipt vouchers directly, match/reconcile vouchers, print documents and their journal entries, request permission to reset posted documents |
| Restricted staff: Accounting Preparer | Prepare and submit for independent approval; cannot post their own document |
| Accounting Approver | Approve/post or return someone else's restricted submissions |
| Accounting Monitor | Read records and documents in the permitted scope |
| Internal accountant outside Preparer/Approver | Continue using the native Accounting application and existing permissions, without the new submission step |

These roles do not imply internal-user or native accounting groups. Portal
accounts must be linked to employees. Internal staff need their existing
native accounting/voucher permissions in addition to any optional review role.
Internal users cannot use the portal accounting routes: page requests return
to the backend and portal API requests are rejected. The backend no longer
contains an Open Accounting Workspace button.

Preparer can be combined with Approver, but that person cannot approve their
own submission. If Direct Posting and Preparer are both assigned, Preparer
wins and independent review is required. Direct Posting plus Approver allows
a regular accountant to post their own ordinary documents and independently
review restricted colleagues' submissions.

## Upgrade and configure

1. Replace the addon folder, restart the server and upgrade the module.
2. Keep the company's journal selection under Accounting > Configuration >
   Settings > Employee Portal Accounting. Existing selections are retained.
   Empty selection denies portal accounting access. The old company-wide
   internal-review checkbox is no longer used; review is role-based.
3. For a REGULAR portal accountant, select Accounting User (Direct Posting)
   and remove Accounting Preparer. For a restricted employee, keep Preparer.
   Assign Approver only to the people who review restricted submissions.
   This upgrade does not assign or remove user groups automatically.
4. Internal staff use native forms. Restricted preparers have Submit for
   Approval. Independent approvers have Approve & Post / Return for Correction;
   enter the return reason in Accounting Review / Reset Requests. Native
   posting warnings and PO overpayments require explicit confirmation.
5. Existing accounting documents already awaiting approval remain protected;
   the upgrade does not silently post or release them. Existing documents with
   an issuer from the previous release are marked as requiring review.

Internal Preparer restrictions apply to manual vendor bills/credits,
miscellaneous entries and vouchers. They also apply outside the portal journal
selection. Native approvers review such records through their existing native
company/model permissions. Portal users remain limited to the explicit journal
selection and permitted companies. No sales-invoice creation/editing is added.

## Reset to Draft

Every portal posting role can REQUEST a reset with a reason; none of these
roles resets a posted document directly through the portal. The request keeps
the accounting document posted, stores the requester/reason, adds a note and
creates activities for existing internal Accounting Managers in that company.
The permission request is administrative metadata; voucher amounts and posted
journal entries remain immutable.

An authorized internal user opens the native document and uses its EXISTING
Reset to Draft button, including existing Studio approvals, lock-date and
reconciliation checks. A reset request does not grant Studio approval, does
not call button_draft, and does not execute the reset. This module does not
replace the existing Studio rule or create approval on the user's behalf.
The native reset clears the pending request once the document becomes Draft.

The staging bill inspected has a Studio approval named
“Request Reset to Draft – Vendor Bill”, with Kinan Ammar as approver and user
to notify. That configuration was inspected without modification. Its full
Studio execution is not reproduced by the local Community test environment.

## Activity history and printing

Portal create/write operations retain the employee's actual create_uid and
write_uid. Completed saves, posting, review/return, attachment additions and
reset requests add notes with the acting employee as author. Native state
tracking continues to operate. The portal Activity Log reads the document's
chatter; internal staff see it in the normal chatter. This is document action
history, not a keystroke log or an immutable external audit ledger.

Print PDF keeps the document report. Print Journal Entry prints the accounting
move behind vendor bills, credit notes, miscellaneous entries, and posted
payment/receipt vouchers. A voucher needs a posted accounting move first.
The new compact app headers have a clear current section. Desktop cards remain
four per row, and the accounting/PO form styling is retained.

## Existing financial boundaries

Native balance, VAT, lock dates, mandatory analytics, duplicate vendor
references, voucher overpayment confirmation and reconciliation checks remain.
Submitted documents cannot be edited through the portal until returned.
Company/journal/related-record scope, stale-version locks and savepoint rollback
remain enforced. Accounting/Voucher models receive no new generic portal ACLs.
The only new ACL is for an internal-only posting-warning transient wizard;
portal users are explicitly denied creating/confirming that wizard.

CEO payment planning, weekly-plan approval, execution-manager actions and
planned-payment reset approvals retain the existing voucher workflow. Ordinary
accounting posting permission does not execute a bank transfer. Vouchers keep
the existing company's currency restriction; bills retain native currencies.

## Validation

Real local Odoo 18 ORM tests use the full original voucher source. Tests cover
normal direct portal posting for bills/JVs/PVs/RVs, attribution, posted locks,
permission-only reset requests, restricted native and portal submissions,
independent native return/approve, combined roles, native overpayment warnings,
portal/backend route separation, journal report routing, company scope,
accounting/tax/analytic/reconciliation/PO/planning regressions, settings and QWeb.
Actual JavaScript DOM fixtures verify Post/save payloads, approval controls,
readonly monitoring, totals, history, print links and reset request controls.

The local environment substitutes the EPS outer module because full EPS
requires Enterprise components. No Employee Portal Suite source is changed.
The release is not deployed yet. Full live Enterprise/Studio execution and
final browser layout/PDF appearance still need staging verification.

## Workspace update 18.0.1.2.0

Normal Post saves and posts directly; only actual accounting or PO overpayment warnings require acknowledgment. Print Journal Entry reuses the existing system Print JV action `wm_journal_entry_report.account_journal`, including bills and vouchers' underlying journal entries. Install that existing report addon; the portal reports a clear error if unavailable instead of printing a different layout.

New documents default to an allowed purchase/general journal; vendor purchase currency and payment terms default from the supplier. Search More supports scoped paging. Missing required selections show actionable messages instead of a stuck calculation.

Purchase User (All Company Documents) can create a draft vendor bill from a confirmed billable PO when also assigned Accounting User (Direct Posting) or Accounting Preparer. Native purchase invoicing determines quantities, and the configured accounting review rules still apply. Employee Portal Suite is not modified.

## Workspace update 18.0.1.2.2

Fix portal Print JV failing with 403 on Report Action metadata. After validating the portal role, company and requested document, the controller reads the fixed existing JV action's metadata with sudo, matching the already elevated PDF renderer. No portal ACL, group membership or report layout changes.

Local verification: print-route fixtures cover portal metadata denial, bill/voucher/journal report targets, missing or incorrect report configuration, and document authorization before metadata elevation. Python and XML syntax checks pass. These fixtures do not render a real Odoo PDF. Upgrade and verify the downloaded PDF on staging.

## Workspace update 18.0.1.2.3

Accounting submission now explicitly notifies independent Accounting Approvers in the document's company, for both native and portal submissions. Internal recipients must have native write access. Portal recipients must be employee-linked and have the document journal configured for the portal. Attendance-only, inactive, out-of-company and self reviewers are excluded. Missing eligible approvers cause a clear submission error. Internal approvers get a review activity; portal approvers get the addressed chatter notification and optional EPS push delivery. Links open the appropriate native or portal document. Repeated submission does not duplicate activities; leaving review closes the review activities, and resubmission sends a new notification. Posting/returning through either review screen notifies the issuer. Optional push failure cannot roll back review.

Portal bill/credit-note lines and manual journal items now use compact spreadsheet-style rows. Enter advances one editable column, Shift+Enter moves back, and Enter at the final editable cell adds the next line. Dropdown selection finishes before navigation; typing and grid focus survive redraws. Foreign amount, maturity date and tax grids remain in a journal item's Details form. The saved bill Journal Preview remains a native-generated, read-only view.

Products can be created or opened/edited from the product dropdown or open icon. The product form includes expense account, purchase taxes, category, units, cost, description, inventory tracking and billing policy. Product edits preserve negotiated bill quantity, price, description and taxes while refreshing the product/account selection. Product writes require an Accounting Preparer/Direct Posting role and configured workspace; company scope, fixed fields, version checks, template/variant locks and other-company tax preservation are enforced. The existing Print JV fix is included.

Local validation: all Accounting Python AST/XML parsing and JavaScript syntax; actual route, notification-transition/recipient, product gateway, existing frontend and grid frontend fixtures. These fixtures substitute the ORM/DOM, mail and push services. No Odoo database, real PDF rendering, actual browser layout or live notification delivery was tested for this release. Upgrade and complete staging checks before production use. Employee Portal Suite, Purchase and Sales are unchanged.

## Workspace update 18.0.1.2.4

A vendor bill or vendor credit note must have its Bill Date before entering accounting approval. The shared review transition validates the date for native and portal submissions, and approval rechecks it for older submitted records. Portal submission gives an immediate date message. Manual journal entries and vouchers do not require a vendor bill date.

Native submission locks and rereads documents, rejects already pending submissions, and validates the complete selected batch before sending review notifications. Its success message is short and nonsticky, followed by a form reload so the Submit button disappears and the approval controls reflect current state.

An independent internal Accounting Approver may correct a pending draft (including reference and journal lines) and approve/post the corrected version. These edits keep the bill Awaiting Approval. Native accounting write permissions still apply. Issuer edits, attendance-only users, portal actors and changes after approval do not qualify for that exception and continue to require resubmission. The shared date guard still blocks posting an undated bill. Existing bills already returned under the old behavior must be corrected/resubmitted once; no historical review status is rewritten.

Local regression fixtures cover missing dates, duplicate submission, batch prevalidation, the toast/reload action, native reviewer versus issuer edits, child-line create/write/delete, notification transitions, portal form submission, grid, products and Print JV. Native Odoo integration cases were updated but cannot be executed in this workspace. No live Odoo/browser/mail/PDF verification was performed for this release. Includes all Accounting 18.0.1.2.3 changes; Employee Portal Suite, Purchase and Sales are unchanged.

## Workspace update 18.0.1.2.5

Portal columns now match the supplied native screenshots in order:

- Invoice Lines: Product, Account, Analytic, Quantity, Price, Disc.%, Taxes, Amount, Company Currency.
- Journal Items: Account, Partner, Label, Analytic Distribution, Taxes, Debit, Credit, Tax Grids.

Description and UoM remain editable from the invoice row's ellipsis (line details), without extra default columns. Product opening/creation/editing and keyboard navigation remain available. Analytic cells show scoped analytic account names. Journal taxes and tax grids appear inline; manual journal tax selections are validated by company and passed to Odoo's native accounting engine. The bill's saved Journal Items tab uses the same eight journal columns and remains read-only so computed tax/payable lines are not rewritten through invoice editing.

Company Currency is the actual company currency name, independent of document currency. Row controls use an unlabeled utility cell. No changes to internal form columns or to Employee Portal Suite. All earlier Accounting fixes are included.

Local checks cover exact invoice/manual-journal/saved-bill-journal header order, analytic/tax/grid values, row navigation and focus, product edit preservation, journal tax/grid scope and serialization, analytic label scope, Python/XML/JS syntax and prior approval/date/notification/Print JV regressions. These are ORM/DOM fixtures. Live browser layout and native tax computation still require staging verification; no live Odoo test was run for this release.
