# Staging browser retest — 7 October 2026

Environment: kinan-absar-odoo-custom-staging-38750536.dev.odoo.com. Only staging was used. Each Apply Selected test used one record. Changes were verified by opening/reloading the actual Planned Payment in a separate browser tab.

The upgraded release displayed Amount Reviewed and the corrected apply behavior. The installed server manifest version was not separately read. UI fixes packaged as 18.0.2.46.0 have not yet been installed or browser-tested.

| Function | Result | Exact record / before / after |
|---|---|---|
| Run new review | PASS | Review #7: 91 recommendations, 26 safe; list header works without selected records. |
| Existing supplier payments | PASS | Mada becomes Keep after conversion; JAWDAH becomes Keep after Add. |
| Supplier/account Add | PASS | JAWDAH INDUSTRIAL COMPANY: no existing matching plan; new plan #338, 40.60, Planned, Not Sent, bill BILL/2026/02/0047 linked. |
| Ordinary Update | PASS | Arkan Al-Saif Company plan #335: controlled forecast change 8.00 to 7.00; review #9 Update restores 8.00; Planned, Not Sent; bill BILL/2026/02/0008 linked. |
| Remove | PASS | Sakinat Albunyan plan #12: 56,846.46, Planned, Pending CEO Review -> Cancelled, Not Sent; amount retained. This cancels rather than deletes. |
| Convert to Payable | PASS | Mada Alesnad For Trading plan #2: PO 146 linked, 93,070.70 -> PO link cleared, PO due 0.00, forecast 93,070.70; 21 bills retained; Planned, Not Sent. |
| Missing PO / PO Add | PASS | PO 225: no existing plan -> new #339, 7,302.96, Planned, Not Sent. Apply first blocked explicitly until Amount Reviewed was checked. Installment correctness was not independently confirmed from contract terms. |
| Unsafe selection | PASS | PO 141 Review: explicit cannot-apply dialog, no selected changes applied. Partially invoiced obligation remains for manual review. |
| Empty selection | PASS | Explicit Select at least one recommendation first dialog. |
| Aged-payable display | PASS (display) | Sakinat: net -45,742.75, advances/credits 102,589.21, gross unpaid invoices 56,846.46. Gross buckets are no longer mislabeled as net payable. Ledger reconciliation was not repeated in this retest. |
| Year filter | PASS (sample) | Review #9 switched 2026 -> 2025: 99 recommendations; 2025 missing PO candidates appear; undated active Arkan/JAWDAH plans remain detected, avoiding duplicate Add. |
| Duplicate prevention | PASS (sample) | Existing JAWDAH is Keep after refresh/year change. A stale Add snapshot tested against a newly created matching plan raises an explicit already-exists error; no second active plan created. |
| Multiple POs | PASS (recommendation sample) | شركة سواعد المشيدون للمقاولات remains Review for its multi-PO plan; agent does not automatically split/consolidate it. Multiple sequential conversions were covered offline, not repeated live. |
| Apply navigation | FAIL in installed release; fix prepared | Successful Apply opens another action-1349 and appends Recommendations breadcrumbs. Cause: notification params.next returned action_open_recommendations(). Fix: existing controller reload callback via act_window_close. |
| Checkbox alignment | FAIL in installed release; fix prepared | Native selector cell vertical-align middle while data is top-aligned. Cause: descendant selector does not match arch class on the list root. Fix: same-root selector and consistent top padding/alignment. |

## Applicability and errors

Add, Update, Remove, and Convert were all applied individually and persisted. New PO Add requires explicit Amount Reviewed. Review/Keep, incomplete signing, partially invoiced conversions, locked payment states, duplicate candidates, and stale balances cannot be automatically applied. The server checks current eligibility rather than silently trusting stored can_apply. The tested empty/unsafe/unconfirmed/duplicate cases all reported errors. No silent skip was observed in the upgraded release's tested cases. Approved/paid locks and changed balances are offline regression coverage; they were not exhaustively exercised live this turn.

## Secondary original-scope checks

Retention Update #288: 44,000.19/Pending CEO Review -> 44,000.14/Not Sent. For a controlled Add test, #288 was then cancelled; new #340 created at 44,000.14, account 201019, five bills linked. A second review made before that Add was rejected as a duplicate after #340 existed. Only #288 Cancelled and #340 Planned were found.

Remaining limitation: amount-only Update preserves an existing incorrect account (old #288 used 203001). New #340 uses 201019 correctly. Source: Update writes forecast/status but does not normalize account_id. Recommended future fix: explicitly validate and correct the retention account when updating a retention plan. This release does not change that logic.

Test changes were left on staging: #338/#339/#340 created, #12 cancelled, #2 converted, #288 cancelled after the controlled test; #335 restored to 8.00. No production changes or payments executed.
