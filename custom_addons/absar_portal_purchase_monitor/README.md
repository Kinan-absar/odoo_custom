# ABSAR Portal Purchase Workspace — 18.0.1.5.0

A dedicated employee-portal purchasing interface, following the Purchase app's familiar navigation, document layout and workflow. This replaces the 1.4 native-backend host. It does not promise every internal purchasing, accounting, stock or signing function.

## The reported error

The supplied screenshot identifies `purchase.order.retrieve_dashboard` raising `AccessDenied`. The native Purchase dashboard refuses the portal identity. This release removes that client/dashboard path rather than bypassing the check or granting Internal User/Purchase User membership.

Only the normal website/portal frontend assets are loaded. Dedicated portal controllers handle named operations; no generic model/method dispatcher, backend action service, native form rendering or backend asset bundle is exposed by this addon.

## Portal experience

- Requests for Quotation, Purchase Orders, Products, Material Requests, Approvals and Confirmations navigation, according to roles.
- Full-width desktop lists, search, status filters, sorting, grouping and paging; responsive mobile layout. Confirmed orders move out of the preparer's RFQ list into Purchase Orders.
- A document sheet with vendor/reference/project/MR/currency/date fields, a purchase status bar, and Products, Other Information, Payments and Signing Package tabs.
- Product lines, descriptions, quantities, UoM, prices, discounts, purchase taxes, sections, notes, catalog selection and line reordering. Tax totals use actual Odoo calculations, with estimates clearly labelled until calculation completes.
- Analytic distribution supports composite rows across plans, one account per plan per row and validated 100% totals. Expense-account override is optional; normal product/category accounts remain the default.
- A shared product creation dialog on both the RFQ form and Products directory: goods/service, inventory tracking, category, UoM/purchase UoM, internal reference, barcode, cost, purchase description, purchase taxes, expense account and bill-control policy. Existing master products are not editable through this portal.
- Material Requests shows only approved requests requiring a PO, in the employee's assigned projects and selected permitted company. Material details can be expanded before choosing Create RFQ.
- Create RFQ from an MR opens an **unsaved** form with project/MR/source and requested descriptions, quantities and units. An existing product is preselected only for one exact name match with a compatible UoM category. Missing/ambiguous products are highlighted for selection or explicitly authorized creation. No products or POs are automatically created by opening a page. Selecting an MR on the form can set its project; importing/replacing lines is an explicit action.
- Save Draft, Submit, Approve/Return and Confirm remain distinct actions. Approval never confirms a PO. Self-approval and editing another preparer's RFQ are rejected. Native double validation remains an internal manager step where configured.
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

A post-migration guard aborts the upgrade if this addon's native access metadata remains. The legacy Native Workspace Access group is retained as an inert compatibility identifier and grants no new rights. There is no native ACL CSV in this version. The old native controller/model extensions are not imported, even if stale files remain on disk after an overlay copy. Old `/purchase/app/…` bookmarks redirect to dedicated portal pages.

The existing 1.3 migration is retained for older installations: compatible legacy projects are mapped only into empty real project fields, and approvals lacking an independently recorded approver require resubmission.

## Portal roles

| Role | Access |
| --- | --- |
| Prepare RFQs | Create RFQs; edit own draft/sent RFQs with Draft/Returned review status; assigned-project MR workflow. |
| Approve RFQs | Review company portal RFQs; approve/return another preparer's submission. |
| Purchase Monitoring | Read confirmed company orders and financial monitoring. |
| Create Products | Additional permission for a preparer to create purchasing products. |
| Confirm Approved RFQs | Confirm independently approved portal RFQs through Odoo's normal purchasing method chain. |

Accounts must be active, employee-linked and outside Attendance Only. Company, project, ownership, role and workflow checks are enforced at the endpoints and model review actions. POST mutations require CSRF; lookups accept only an allowlist of types. The portal receives no blanket purchasing, product, accounting or HR model ACLs from this release.

## Install / upgrade on staging

1. Back up staging and keep the previous addon revision. Replace the technical folder `absar_portal_purchase_monitor` in the custom-addons branch; EPS itself is unchanged.
2. Let the Odoo.sh build/restart complete, then upgrade **ABSAR Portal Purchase Workspace** in Apps. A file replacement without a restart/module upgrade does not execute the permission withdrawal.
3. Verify version `18.0.1.5.0`. Existing Portal account types and purchasing roles remain unchanged. Native Workspace Access is no longer needed.
4. Hard-refresh the portal. Use the Purchase sidebar links or `/my/employee/purchase` for a preparer. Confirmers/reviewers can use their dedicated links; monitoring users can open Purchase Orders.
5. Verify that the old native model ACLs/rules are gone and the native host is no longer served. Then complete the acceptance checks below on staging.

Dependencies: `employee_portal_suite`, `purchase_stock`, `project_purchase`, `account`, `mail`, `analytic`. The standard project-purchase integration supplies the actual `project_id` field. The addon retains its technical name and old portal XML IDs for upgrades.

## Validation and remaining work

Executed locally:

- Python compilation, XML/QWeb expression parsing, manifest/asset/import path checks, authenticated/CSRF route checks, EPS navigation inheritance and retained portal XML IDs.
- JavaScript syntax checks for all four frontend modules.
- 50 isolated validators/approval/financial-allocation checks (`tools/check_logic.py`).
- 60 portal-boundary, route and migration checks, plus two post-migration checks and eight MR proposal/matching/line-cap checks (`tools/check_portal.py`). The actual pre-migration SQL was run against disposable SQLite tables to check module ownership, literal prefixes, unrelated-record preservation, fresh-install behavior and idempotency. The actual post guard was exercised with fixtures to check fail-closed behavior.

**These are not Odoo/PostgreSQL installation tests or browser execution tests of 1.5.** The complete EPS/Enterprise runtime is not installed in the artifact-building environment. The new package has not been deployed to staging by the agent. Existing read-only staging inspection confirmed the native dashboard failure; it does not validate this replacement's runtime.

After an authorized staging upgrade, test:

1. Portal identity, old native-grant removal and access for separate Prepare/Review/Confirm/Monitor users. Direct generic RPC must retain the permissions provided by standard Odoo/other addons, without the 1.4 grants.
2. List navigation, search/group/paging, mobile/desktop layout and read-only states.
3. Vendor defaults, company/currency/UoM changes, catalog, new product creation, multiple lines, taxes, discounts, totals and two-plan analytic allocation.
4. Assigned approved MR import, unmatched/ambiguous products and invalid/other-company/unassigned/no-PO-required MRs. Up to 300 lines per RFQ are supported.
5. Draft save, stale-version rejection, submit, independent review, return/resubmit and optional confirmation/double validation. Confirm can create receipts and trigger installed automation; use only authorized test data.
6. PDF upload/download scope, wrong-order attachment denial and printed RFQ/PO output with the installed custom report stack.
7. Existing payment/signature monitoring against real linked documents. Custom signing/report/calculation hooks need acceptance with the actual installed extension versions.

## Licensing

This release keeps the UI and access paths within a dedicated portal implementation and does not turn an account into an Internal User or modify subscription verification. **That is not a guarantee of licence exemption.** Odoo must confirm how employee purchasing activity is classified under ABSAR's actual subscription agreement; changing the interface or keeping a Portal label alone cannot establish contractual compliance.
