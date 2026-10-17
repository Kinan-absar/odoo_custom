# ABSAR Portal Purchase Workspace — 18.0.1.3.0

Separate Odoo 18 addon. Technical folder: `absar_portal_purchase_monitor`.

**Status: rebuilt and checked locally; staging installation and acceptance testing are pending.**
This package has not been installed into the supplied staging database. No staging records were created, approved, confirmed, signed or deleted during the rebuild. The live portal page returned 403 for the current Kinan session during inspection.

## Changes from 18.0.1.2.0

- Complete New RFQ form with header, Products, Other Information, Payments and Signing Package tabs. Desktop layout follows the inspected ABSAR backend, with responsive controls for mobile.
- Saves actual purchase orders and lines. Existing line IDs are retained on editing. Product, section and note rows can be added, removed or reordered before saving the complete draft.
- Uses the actual `project_id` when installed and EPS's actual `material_request_id` relationship. Source Document remains separate. MR choices follow the employee's assigned work-location projects, the selected project and company.
- Searchable vendor, product, UoM, tax, project, buyer, account, analytic and accounting-option lookups. Catalog has search, add controls and incremental paging.
- Native vendor onchanges supply currency, payment terms and fiscal position. Native purchase line computations/onchanges supply vendor prices, taxes, lead times and descriptions. Explicit quote prices remain editable. Existing quoted prices are retained until the preparer applies vendor defaults. Preview uses in-memory records; Save Draft persists them.
- Actual Odoo tax/amount computation supplies recalculated totals, including configured tax/discount behavior. Unsaved totals are explicitly labeled estimates until recalculated.
- Multi-row analytic distributions support one account per plan per row, account combinations, percentages and per-plan 100% totals. Native mandatory-plan validation is invoked at submission.
- Explicit expense-account override is validated against company and allowed account types; defaults remain product/category-driven. Invoice preparation maps the explicit account through the fiscal position.
- Save Draft, Submit, Approve/Return and Confirm are separate actions. Approval never calls confirmation. Self-approval is rejected. A dedicated additional permission is needed to confirm through the native purchase workflow; native double validation is not auto-approved.
- Resetting a portal order to draft clears old review approval. Backend edits to unconfirmed RFQ contents invalidate submitted/approved review. Optimistic version checks and row locking protect against stale saves and competing decisions.
- Read-only monitoring shows actual signing status text when available and keeps explicit PO-linked payments separate from allocated bill settlement. Posted vendor credit notes reduce net billed amounts. Shared bills are allocated by linked tax-inclusive bill-line proportions; bill amounts are converted to PO currency at bill date.
- Search, status filters, sorting, grouping and 20-record paging on purchase lists. Groups are ordered across the result set and may continue onto another page.
- Chatter notifications, internal review activities and optional EPS WebPush are used for submission/approval/return. Optional push failures do not roll back a valid purchase decision.
- Legacy projects are migrated only into empty real project fields with compatible companies. Existing real project values are preserved. Legacy unconfirmed approvals without an identified approver require resubmission; approval history is never invented.

## Permissions

Existing group XML IDs are retained on upgrade. No group is automatically granted to any user, and no group implies backend purchasing, accounting, HR or product ACLs.

| Group | Permission |
|---|---|
| Purchase - Prepare RFQs | Create RFQs; edit only own draft/sent RFQs whose review is Draft or Returned. |
| Purchase - Approve RFQs | Read/review company portal RFQs; approve or return another preparer's RFQ. Does not grant edit or confirmation. |
| Purchase Monitoring (Read Only) | Read confirmed/locked company POs and their monitoring details. |
| Purchase - Create Products | Additional permission for a preparer to create purchasing products. |
| Purchase - Confirm Approved RFQs | Additional permission to confirm an independently approved portal RFQ through `button_confirm()`. It can create receipts and trigger installed automation. |

Users must be active, linked to an employee, and not Attendance Only. Company boundaries use the user's permitted companies. Broad monitoring/approval combined with preparation never grants editing of someone else's RFQ.

Portal users receive no generic elevated model RPC. Controller lookups and writes use narrowly scoped elevation after role, company, ownership, workflow and related-record validation. Mutations are POST-only with CSRF protection. The original unsafe/name-only product route and add/remove/header-only mutation routes have been removed.

Confirm permission is optional. Without it, an authorized internal purchaser completes native confirmation from Purchase after portal review approval. If native confirmation requires a wizard, the portal rolls its transaction back and asks for backend completion. Signature sending and approval rules in installed extensions remain in their normal native method chain; this release never writes native purchase or signing state directly.

## Installation / upgrade

1. Extract the ZIP. It contains exactly one top-level addon folder: `absar_portal_purchase_monitor`.
2. Replace that folder in the custom addons repository branch linked to the chosen staging database. Keep the technical folder name unchanged. Employee Portal Suite itself is not replaced or modified.
3. Let Odoo.sh build the staging branch, then upgrade **ABSAR Portal Purchase Workspace** in Apps. An existing installation must be upgraded, not merely have its files replaced. Restarted workers and updated frontend assets are required.
4. Confirm the installed version is `18.0.1.3.0`. Reload the portal to load the new assets.
5. Check dedicated group assignments for preparer, reviewer and monitor test accounts. Grant optional product-creation/confirmation roles only to designated users. No role changes were made by this package.
6. Complete the acceptance checks below before treating this as production-validated.

Declared dependencies: `employee_portal_suite`, `purchase_stock`, `account`, `mail`, `analytic`, `project`. `purchase_stock` is explicit because receipts and operation types are part of this workspace.

The inspected staging's Purchase project field comes from an existing installed integration. The addon uses that exact field if present; it does not introduce a guessed second Project relationship. If it is absent, project selection gives a configuration error and the page shows a notice. The existing legacy portal project field is retained only for upgrade safety.

## What was verified

- Live backend inspection: RFQ PO 240, confirmed PO 238, RFQ and Purchase Order lists, new unsaved RFQ, inline product editing, analytic allocation popup, product-create defaults, product Accounting/Purchase tabs, Other Information, Payments and Signing Package.
- The unsaved product/RFQ used for inspection were discarded.
- Python syntax and XML parsing; 150 QWeb/view expression syntax checks.
- Manifest data/asset paths; navigation inheritance XPath targets against the supplied EPS source; retained external IDs.
- JavaScript syntax with `node --check`.
- 50 isolated checks executing actual addon validation, approval and financial calculation methods with fixtures: invalid numbers/IDs, multi-plan percentages, duplicate combinations, same-plan collisions, unavailable accounts, timezone/DST errors, self-approval, approval without confirmation, missing approver, shared bills, draft-bill exclusion, credit notes, currency conversion, advances and mismatched linked-payment currencies.

Run the included isolated logic checks with:

```bash
python3 absar_portal_purchase_monitor/tools/check_logic.py
```

These isolated tests do **not** initialize Odoo and do not prove ORM, QWeb rendering, installation, company-dependent fields, ACLs, custom onchanges or browser integration.

## Pending staging acceptance checks

Obtain permission before saving clearly labeled test records. Use separate existing employee test accounts with the appropriate roles.

1. Upgrade/install without registry, view inheritance or asset errors.
2. Confirm preparer-only, approver-only, monitor-only, combined-role, Attendance Only and unrelated-user access. Check direct record URLs and forged POSTs across owners/companies.
3. Create an RFQ with vendor terms/currency, assigned project, linked MR, delivery type and multiple lines; edit/reorder/remove existing lines; reopen and verify native records.
4. Check vendor-specific quantity/UoM pricing, custom onchanges, fiscal positions, native tax rounding, discounts, arrival dates and cleared header values.
5. Check both installed analytic plans, split/composite allocations and mandatory-plan behavior. Verify explicit expense-account behavior against the installed Studio/custom Division accounting logic.
6. Verify product-create permission and native defaults for goods, tracked goods and service products; confirm ordinary preparers cannot create products.
7. Submit, reject self-approval, approve without confirming, return with a note, edit/resubmit, and separately confirm. Test native double validation and a stale competing save/decision.
8. Verify the installed signing core/PO addon still applies its exact director/CEO workflow, package attachments and custom confirmation hooks. Confirming a PO and completing its signatures remain distinct states.
9. Compare monitoring with real vouchers, Odoo payment allocations, advances, mixed-PO bills, partial settlements, credit notes and foreign-currency orders. Verify no payment is counted twice.
10. Check EPS notifications, desktop/mobile rendering, keyboard lookup navigation and assets after cache refresh.

## Known limits / dependencies not yet verified

- No Odoo runtime is installed in the local validation environment. Staging installation, native computations/onchanges, frontend interaction and role testing have not run against this rebuilt version.
- The current installed signing core, PO Send-to-Sign and payment-allocation addon sources were not supplied. Their exact hooks and financial semantics are therefore not certified. Existing observed field names are used; alternate field names are not guessed.
- New signing requests, supplier-quotation upload/selection, vendor payments, receipts, bills and print/direct-print actions continue in their existing backend interfaces. The portal Signing Package tab shows status/attachment names, not a new signing wizard.
- Studio Tags/Subcontractor and the unidentified custom Division/cost-account field are not made editable in the portal. The supplied source does not define their business behavior. Existing values are preserved on existing records.
- Existing rich-text terms are preserved when unchanged. Edited terms are saved as safe plain text inside native HTML, so editing terms does not reproduce the backend rich-text toolbar.
- The portal catalog reproduces product selection/search/add behavior; it is not the backend's full stock-availability catalog.
- Linked Paid uses the installed `amount_paid` only when its declared currency matches the PO currency. Otherwise it is shown as unavailable. No conversion rate is invented for an aggregate payment amount with unknown payment dates.
- Billed due and bill settlement are proportional allocations for mixed bills. Settlement can include credits/write-offs and is not represented as cash paid. Native rounding or exceptional zero-net mixed bills need reconciliation during acceptance testing.
- A native `to approve` order stays in native purchasing approval; the portal does not automatically run native manager approval. Cancel/reset/sign actions remain in the backend.
- This is a staging candidate, not a claim of a perfect or production-tested module.
