# Payment Review Agent 18.0.2.45.0

## Changes

- Run Payment Review works as an Odoo recordset/object button, including an empty list selection.
- Apply Selected uses the native selected recommendation records and current eligibility. Unsafe, already applied, locked, or stale recommendations raise explicit errors instead of silently skipping. Success reports the applied count and returns to the same review.
- Pending, held, and rejected planned payments can be revised; their CEO decision is reset to Not Sent. Approved/adjusted and executed payments remain locked.
- Generated values no longer overwrite computed eligibility. Opening an existing review refreshes eligibility; applying always validates live values.
- New PO payments require Amount Reviewed after checking the proposed installment. Changing the amount clears this confirmation. Unsigned, billed, draft-billed, or over-budget PO candidates cannot be added automatically.
- Conversion clears the PO relationship or updates the current supplier-balance target and cancels the old PO plan. Partially invoiced POs stay manual so the remaining obligation is not discarded.
- Retention reads Odoo 18 product lines, posted invoices/refunds, actual PO source lines, and account 201019. Completion is checked in PO currency and does not use Billing Status. Company-currency retention is cross-checked against the posted supplier GL.
- Retention control includes all years and all PO states. Mixed invoice sources, unidentified releases across several POs, floating retention plans, and multiple plans for the same PO require manual allocation.
- Duplicate checks include commercial suppliers and all active years. Undated plans remain visible in year-filtered reviews. Active multi-PO plans block a potentially overlapping supplier-balance Add.
- Aging distinguishes signed net balance, advances/credits, and gross unpaid invoice buckets.

## Installation and verification

Replace the existing addon source with this directory and upgrade internal_transfer_voucher on staging. Run a NEW Payment Review after upgrading: old recommendation amounts/reasons are historical snapshots.

33 standalone offline regression checks passed, executing the changed methods with lightweight ORM doubles. Python compilation and XML parsing passed. These checks do not verify installation, Odoo computed-field scheduling, browser behavior, or actual database transactions.

Run the included checks with:

    python3 quality_checks/offline_regression.py

This release has not been installed or browser-retested on staging. Repeat individual Add, Update, Remove, Convert to Payable, and Add Retention tests after upgrade. No production deployment was performed.
