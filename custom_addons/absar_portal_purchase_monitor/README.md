# ABSAR Portal Purchase Workspace — 18.0.1.5.7

A dedicated employee-portal purchasing interface, following the Purchase app's familiar navigation, document layout and workflow. This replaces the 1.4 native-backend host. It does not promise every internal purchasing, accounting, stock or signing function.

## Portal approval attention in 18.0.1.5.7

Internal To Do activities are supplementary. Every eligible portal or internal Approver can see submitted RFQs through the shared queue, independently of native mail activities or a device push subscription. Purchase approvals now appear in the portal notification bell, sidebar count and home Needs Your Attention card. The summary uses the same company, independent issuer, RFQ state and submitted review conditions as the default approval queue; issuer-only, monitor-only, Attendance Only and inactive accounts receive no approval counts.

Opening the approval queue acknowledges the new indicator while retaining the pending home/sidebar count until the request is resolved. Returning, resubmitting or confirming a request updates the persistent count. These markers reuse EPS's existing notification model; no generic purchase or HR access is granted. Existing pending requests are counted after upgrade as well as new submissions.

The native Purchase Review tab and portal submitted banner show **Eligible Approvers**, including portal and internal accounts. The displayed list and submission recipients use the same eligibility helper. This is a group review pool, not an assignment to only the native To Do activity's user. Portal Submit is labelled **Submit for Approval**, matching the internal form; Approve Only is explicitly labelled separately from Approve & Confirm.

Browser checks on staging were limited to the signed-in Fahed Issuer account: RFQ list/status, read-only submitted order and displayed totals, purchasing product form defaults, and unsaved MR-to-RFQ import. No staging order/product was saved or confirmed. Switching to another account was blocked by automatic approval review, so live internal/Approver checks and the final deployment still require authorized access. Local Odoo/PostgreSQL tests cover internal creation, submission, shared portal review/return/resubmit/confirmation and the role/company/notification boundaries. The runtime uses the actual EPS seen-marker fields/helpers with a minimal base summary bridge; it does not run the entire EPS/Enterprise stack.

## Internal and portal submissions in 18.0.1.5.6

Both internal and portal issuers use the same request/approval fields, queue and Approver role. In native Purchase, the original Confirm buttons now say **Submit for Approval**. Submission records the issuing account as Issuer and Buyer and leaves the RFQ in Draft/Sent with Awaiting Approval status. An Approver opens **Requests to Approve** in Purchase, or **Purchase Approvals** in the portal, and chooses **Approve & Confirm** (or returns it with a correction note). Approve Only remains optional; it requires the separate Confirm Approved RFQ action afterwards.

The original `button_confirm` method also routes unapproved RFQs to submission, so an existing server action or direct call cannot silently confirm an unreviewed native RFQ. Direct `button_approve` cannot skip independent review. This applies to native confirmation callers as well as the form; integrations that previously confirmed RFQs automatically must now use the shared submission/review process. Submitted RFQs cannot be submitted again or confirmed by their issuer, even if that issuer also has Approver rights. Changes to submitted/approved content invalidate review and require resubmission.

An internal issuer can submit their own assigned-buyer RFQ; another buyer's draft cannot be claimed. Portal issuers remain employee-linked; internal issuers may use their existing account without an employee record. The upgrade adds Issuer to existing internal Purchase Users without altering their account type. On fresh installations or for new purchasers, assign Issuer explicitly; Approver remains a separate role. Previously confirmed orders and their financial documents are not reopened.

Studio approval rules are not removed or edited by this addon. Remove a redundant Studio rule separately when switching to the shared workflow. Odoo's company-level two-step purchase validation is also separate: above its threshold, a portal Approver without native Purchase Administrator rights may still leave an order To Approve. The installed signing, stock and native validation chain remains in place.

## Unified roles and original monitoring design in 18.0.1.5.5

Only three addon groups remain: **Issuer**, **Approver**, and **Monitor**. Each role can be assigned to either a portal or internal account. Roles do not imply Internal User, Purchase User or Purchase Administrator, and add no generic model ACLs. Normal Odoo groups remain separate.

- **Issuer** creates RFQs and purchasing products, edits own eligible drafts, and submits for independent approval. **Submit for Confirmation** keeps the native RFQ in Draft/Sent with review status Awaiting Approval; submission never confirms or creates receipts.
- **Approver** reviews another issuer's request, returns it with a note, approves only, or explicitly chooses **Approve & Confirm**. The dedicated portal uses the same group as the internal form. Existing internal users retain their normal backend access requirements. Native confirmation, stock, double validation and installed signing hooks continue to run; unsupported backend wizard responses roll back the portal transaction.
- **Monitor** retains the original Purchase Monitoring list and read-only PO design, including financial summary cards, project/MR information, signing status and order lines. The Purchase Orders link and confirmed-order bookmarks send monitors to that layout. Corrected posted-bill/refund, currency and allocation calculations remain in use.
- Buyer is the preparing employee's existing account, remains read-only in the portal and appears in lists. No account type is changed.
- Upgrade merges old Confirm Approved RFQs memberships into Approver and old Create Products memberships into Issuer. Their external identifiers become aliases to the retained groups. The retired native-host group is removed. Existing Purchase Administrators receive the Approver role to preserve the approval authority they held in 1.5.4. No internal group is granted by this migration.

The internal Portal Purchase Review tab remains last, after Signing Package. Portal approvers receive the portal approval link; internal approvers also receive a review activity. Self-approval, other-company requests and editing another issuer's RFQ remain blocked.

## Layout change in 18.0.1.5.3

Move the backend Portal Purchase Review fields and existing review buttons into a final notebook tab, following Signing Package. The inherited view appends the page at priority 1000, after the standard purchase/signing extension views. The tab remains visible only for portal-prepared orders.

## Fixes in 18.0.1.5.2

The reported zero amounts and draft-save failure were reproduced with actual Odoo 18 models and PostgreSQL.

- Defaulting a product line automatically attaches a temporary line to the virtual parent via the inverse relation. Reusing that parent for preview duplicated the products and reset prices. Preview now constructs a fresh parent containing exactly the validated submitted rows, then runs native amount/tax calculations.
- Section/note payloads omitted `product_qty`. Odoo's SQL field is NOT NULL even for these rows, producing `NotNullViolation` on draft creation. Sections/notes now explicitly supply zero quantities/prices and empty product/accounting fields.
- Existing RFQs now settle vendor/currency/header-dependent native computations before applying the validated line changes. This preserves manually entered prices and discounts when quantities or the vendor change.
- Existing company-wide project/MR choices, product creation, portal roles and native-host withdrawal remain in place.

## Fixes in 18.0.1.5.1

- Projects and approved MRs requiring a PO cover the permitted company, independent of the preparer’s assigned projects. Selecting an MR sets its project; the server still enforces a matching project and company.
- Remove a local `_` variable that shadowed Odoo’s translation function and caused `'str' object is not callable` when a selection was unavailable.
- Accept False as an empty optional identifier; continue rejecting True, negative and non-integral identifiers. Identifier failures name the affected lookup.
- Serialize persistent origin IDs for product defaults, purchase line relations and vendor defaults. Pseudo-record IDs must not be posted back as database identifiers.
- Recompute virtual line amounts and order totals using native Purchase tax methods after all lines are attached. The totals panel remains present while updating, and async defaults schedule a final calculation after completion.
- Deduplicate product tax selections and validate required product selectors before creation.
- Roll back and log unexpected save/create failures with a reference instead of reporting every server error as a changed session. Expected validation remains visible in the form.

The 1.5 portal implementation replaces the former native dashboard host, whose `purchase.order.retrieve_dashboard` denied portal identities. The migration removing that host is retained unchanged.

Only the normal website/portal frontend assets are loaded. Dedicated portal controllers handle named operations; no generic model/method dispatcher, backend action service, native form rendering or backend asset bundle is exposed by this addon.

## Portal experience

- Requests for Quotation, Purchase Orders, Products, Material Requests, Approvals navigation, according to roles.
- Full-width desktop lists, search, status filters, sorting, grouping and paging; responsive mobile layout. Confirmed orders move out of the preparer's RFQ list into Purchase Orders.
- A document sheet with vendor/reference/project/MR/currency/date fields, a purchase status bar, and Products, Other Information, Payments and Signing Package tabs.
- Product lines, descriptions, quantities, UoM, prices, discounts, purchase taxes, sections, notes, catalog selection and line reordering. Tax totals use actual Odoo calculations. The three total rows stay visible while updating; previous tax/total values are marked pending. Changed line amounts no longer reuse stale cached subtotals.
- Analytic distribution supports composite rows across plans, one account per plan per row and validated 100% totals. Expense-account override is optional; normal product/category accounts remain the default.
- A shared product creation dialog on both the RFQ form and Products directory: goods/service, inventory tracking, category, UoM/purchase UoM, internal reference, barcode, cost, purchase description, purchase taxes, expense account and bill-control policy. Existing master products are not editable through this portal.
- Material Requests shows only approved requests requiring a PO, across the selected permitted company, regardless of employee project assignment. Material details can be expanded before choosing Create RFQ.
- Create RFQ from an MR opens an **unsaved** form with project/MR/source and requested descriptions, quantities and units. An existing product is preselected only for one exact name match with a compatible UoM category. Missing/ambiguous products are highlighted for selection or explicitly authorized creation. No products or POs are automatically created by opening a page. Selecting an MR on the form can set its project; importing/replacing lines is an explicit action.
- Save Draft, Submit, Approve/Return and Confirm remain distinct actions. Approve Only never confirms a PO; the Approve & Confirm action explicitly performs both steps. Self-approval and editing another preparer's RFQ are rejected. Native double validation remains an internal manager step where configured.
- Supplier quotation PDFs can be uploaded to an existing editable RFQ (maximum 1.4 MB), linked to the installed quotation field when present, and downloaded through an order-scoped route. There is no arbitrary attachment/model upload parameter.
- Print PDF renders the standard RFQ or PO report only after checking access to that exact order. Printing itself does not mark an RFQ sent or change approval state.
- Payments/signing information remains read-only. Existing allocation monitoring, posted credits, linked PO payments and installed signing-status text are preserved. Accounting posting, stock validation, signature sending and external vendor emails are not added as portal operations.

Actual orders and products are saved in Odoo's real models through narrowly scoped server operations, with explicit field/record validation. Registered purchasing defaults/onchanges, taxes and confirmation hooks remain server-side; the portal UI is its own implementation. Arbitrary Studio fields and unknown custom extension wizards are not automatically reproduced.

## Upgrade withdrawal of the native host

**Upgrade the same addon in place; do not uninstall it.** Business POs, products, review history and documents are retained.

For upgrades from 1.4.x, the `18.0.1.5.0/pre-migration.py` script:

1. Removes only this addon's `access_native_…` model ACLs and `native_…` record rules, using literal prefix matching and the owning module's XML metadata.
2. Deactivates its native-host/presentation/MR-button/return-wizard views before the old Python extensions disappear.
3. Leaves unrelated modules' grants, role assignments and business records untouched.

A post-migration guard aborts the upgrade if this addon's native access metadata remains. The 1.5.5 migration removes the retired Native Workspace Access group. There is no native ACL CSV in this version. The old native controller/model extensions are not imported, even if stale files remain on disk after an overlay copy. Old `/purchase/app/…` bookmarks redirect to dedicated portal pages.

The existing 1.3 migration is retained for older installations: compatible legacy projects are mapped only into empty real project fields, and approvals lacking an independently recorded approver require resubmission.

## Portal roles

| Role | Access |
| --- | --- |
| Issuer | Create RFQs and products; edit own Draft/Returned requests; submit for approval. |
| Approver | Independently approve, return and confirm submitted requests. |
| Monitor | Read confirmed company orders in the original monitoring layout. |

Accounts must be active and outside Attendance Only. Portal users must be employee-linked. Internal users can use their existing account without an employee link. Company, project, ownership, role and workflow checks are enforced at endpoints and model review actions. POST mutations require CSRF; lookups accept only allowlisted types. No blanket purchasing, product, accounting or HR model ACLs are granted.

## Install / upgrade on staging

1. Back up staging and keep the previous addon revision. Replace the technical folder `absar_portal_purchase_monitor` in the custom-addons branch; EPS itself is unchanged.
2. Let the Odoo.sh build/restart complete, then upgrade **ABSAR Portal Purchase Workspace** in Apps. A file replacement without a restart/module upgrade does not execute the permission withdrawal.
3. Verify version `18.0.1.5.6` and the three named addon groups. Account types remain unchanged; legacy role memberships merge as described above.
4. Hard-refresh the portal. Use the Purchase sidebar links or `/my/employee/purchase` for a preparer. Approvers use Purchase Approvals; monitoring users can open Purchase Orders.
5. Verify that the old native model ACLs/rules are gone and the native host is no longer served. Then complete the acceptance checks below on staging.

Dependencies: `employee_portal_suite`, `purchase_stock`, `project_purchase`, `account`, `mail`, `analytic`. The standard project-purchase integration supplies the actual `project_id` field. The addon retains its technical name and old portal XML IDs for upgrades.

## Validation and remaining work

Executed locally:

- Real Odoo 18 Community core (`1f2b50ad`) and PostgreSQL 16, with this addon's actual purchasing model/controller source and a minimal MR bridge. The full EPS/Enterprise/custom signing stack was not installed locally.
- Reproduced the old preview returning eight rows for five submitted rows and zero totals; reproduced SQL `NotNullViolation` for section `product_qty` during save.
- Verified the corrected preview contains exactly three products, one section and one note, with untaxed 162,930.00, VAT 24,439.50 and total 187,369.50 SAR; verified the same values on a persisted draft.
- Real ORM regression cases for draft create/edit, quantity/price/discount/vendor changes, submit without PO confirmation, issuer confirmation denial, portal and internal Approver approval/confirmation, idempotent role consolidation and internal Issuer migration, native internal submission routed to the shared portal approval queue, prevention of issuer confirmation, Buyer identity, native view/action loading, Buyer migration, product defaults/create/add, and a user remaining Portal without Internal User membership (`tools/odoo_runtime_cases.py`). Fixtures were rolled back.
- Python/XML/QWeb/JavaScript and package checks; isolated validator/workflow, migration scope/idempotency and MR proposal checks; frontend payload, amount-cache and persistent-total-panel tests.

The final ZIP has not been deployed by the agent. The local tests exercise real ORM calculations and writes, not this staging database's complete extension stack or end-to-end browser execution. Staging acceptance after upgrading is still required for custom signing/report behavior and company-specific constraints.

After an authorized staging upgrade, test:

1. Portal identity, old native-grant removal and access for separate Issuer/Approver/Monitor users. Direct generic RPC must retain the permissions provided by standard Odoo/other addons, without the 1.4 grants.
2. List navigation, search/group/paging, mobile/desktop layout and read-only states.
3. Vendor defaults, company/currency/UoM changes, catalog, new product creation, multiple lines, taxes, discounts, totals and two-plan analytic allocation.
4. Company-wide approved MR import, unmatched/ambiguous products and invalid/other-company/unapproved/no-PO-required MRs. Up to 300 lines per RFQ are supported.
5. Draft save, stale-version rejection, submit, independent review, return/resubmit and optional confirmation/double validation. Confirm can create receipts and trigger installed automation; use only authorized test data.
6. PDF upload/download scope, wrong-order attachment denial and printed RFQ/PO output with the installed custom report stack.
7. Existing payment/signature monitoring against real linked documents. Custom signing/report/calculation hooks need acceptance with the actual installed extension versions.

## Licensing

This release keeps the UI and access paths within a dedicated portal implementation and does not turn an account into an Internal User or modify subscription verification. **That is not a guarantee of licence exemption.** Odoo must confirm how employee purchasing activity is classified under ABSAR's actual subscription agreement; changing the interface or keeping a Portal label alone cannot establish contractual compliance.
