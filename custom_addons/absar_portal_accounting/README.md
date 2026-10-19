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
