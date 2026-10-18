# ABSAR Native Portal Purchase Workspace — 18.0.1.4.1

**Native integration candidate; not installed or runtime-validated on staging.** This release replaces the hand-written portal PO editor with an isolated host for Odoo 18's actual action service, Purchase views, form/list controllers, search controls, widgets, catalog and product dialogs. It is not a screenshot replica or an iframe of an impersonated internal session.

The employee remains a Portal user. Normal authenticated ORM calls use actual ACLs, global company/ownership rules and model guards. The module does not set Internal User, imply Purchase User, forge session administrator flags, or expose a generic sudo RPC dispatcher.

## 1.4.1 installation fix

The reported staging upgrade failed because the product view inheritance required the fourth node with an exact UoM group attribute. Installed Odoo revisions/extensions can have fewer such nodes. All numbered/group-dependent Purchase and Product inheritance selectors are removed. Native display-group adaptation now visits only controls actually present in the resolved architecture, while preserving a separate copy and existing access rules. The retained view IDs use only the standard form root as an inheritance target.

The patch includes regression checks for different numbers of UoM controls, absent controls, nested product/line controls, negative fallback groups and unchanged source architectures. These are local checks; a live module upgrade is still required to verify the complete database.

## What changed

- `/my/employee/purchase` loads the installed `purchase.purchase_rfq` action. Purchase Orders and Products use the installed standard Purchase actions. Their inherited views and installed backend assets are loaded rather than copied into portal HTML.
- Standard editable order lines, product selection, purchasing onchanges, taxes, totals, UoM, vendor terms, native analytic distribution, dates, catalog, product forms, attachments and search/paging/grouping run through the actual Odoo components. Expected Arrival remains a standard native field.
- Navigation between native actions and browser history stays inside `/my/employee/purchase/app`. The full internal application menu is not fetched. The employee portal remains available through the header link.
- The real `project_id` comes from the declared standard `project_purchase` dependency. `material_request_id` and MR views/actions come from the supplied Employee Portal Suite (EPS).
- Approved MRs assigned to the employee's work-location projects are available in Material Requests. **Create PO** calls EPS's actual `action_create_po`, with native RFQ defaults for the linked MR, project and company. EPS's supplied backend action links the MR; it does not copy free-text MR lines into products automatically. This release follows that behavior.
- Prepare, Submit, independently Approve/Return, and Confirm remain separate role-controlled operations. Approval never confirms a PO. Return opens an actual native correction-note dialog. Confirm invokes the installed native method chain, including receipts, double validation and extension hooks; it does not write purchase/signing state directly.
- Printing and email composition use the native RFQ actions on the preparer's eligible draft. A server-only identity token permits only the necessary draft-to-sent transition; a caller-supplied context boolean cannot authorize state changes.
- Backend edits to submitted/approved unconfirmed portal RFQs invalidate review. Native analytic validation now runs through Purchase's multi-line helper when submitting.
- Existing read-only purchase monitoring remains available, including allocated vendor-bill settlement, credits, linked PO payments and actual signing status text where installed.

## Explicit permissions

**Native Workspace Access is a new opt-in group. An upgrade assigns it to nobody.** Add it to active, employee-linked Portal accounts together with the required purchase roles. Existing role XML IDs are retained. Attendance Only users cannot use the native workspace.

| Group | Allowed workflow |
| --- | --- |
| Purchase - Native Workspace Access | Enables scoped native ORM access; must be assigned with a purchase role. |
| Purchase - Prepare RFQs | Create RFQs and edit own draft/sent RFQs whose review is Draft/Returned. |
| Purchase - Approve RFQs | Read/review company portal submissions; independently approve or return another preparer's RFQ. |
| Purchase Monitoring (Read Only) | Read confirmed/locked company POs and the separate monitoring pages. |
| Purchase - Create Products | In addition to Prepare: create purchasable company products using the native product form; change own created products/vendor prices only. |
| Purchase - Confirm Approved RFQs | Confirm independently approved portal RFQs through native purchasing methods. |

New purchasing/product CRUD ACLs are attached only to Native Workspace Access. Model guards enforce each additional role even if someone calls JSON-RPC directly. Global native PO/line rules intersect other modules' group rules. Internal and non-opted-in users retain their pre-existing access policies.

Related lookup models are read-only and company-scoped where applicable. Buyer selection returns only names/IDs of permitted internal buyers, with a narrow display/avatar read path; it grants no general `res.users` read access. Products remain purchasable and company-scoped. Custom editable scalar fields and approved types of custom many-to-one fields remain subject to normal field ACLs and related-record company checks. Custom relational collections/automation need their extension source and acceptance tests.

## Important scope limits

The host uses native views, but **this is not verified parity with every internal ability**:

- Vendor bill creation/posting, stock validation, native manager double approval, purchase locking/unlocking and email-template administration remain internal-role operations. Their native buttons may be present; server checks enforce the boundary. Broad accounting, stock and administrator permissions are not silently granted to portal users.
- Purchase monitoring allocates settlement without granting full Accounting access. Opening a bill/receipt through a native smart button can require additional existing read permissions. Those models are not broadly exposed by this package.
- The inspected database has Payments, Signing Package, custom allocations and Studio fields whose complete addon sources were not supplied. Their native views/assets are reused. Custom related-model reads, signing wizards, hard-coded internal-user/group checks, and execution hooks must be validated with the installed extensions. This package does not claim those functions are all working for a Portal identity.
- Native product variants/attribute configuration, new categories/UoM/taxes/accounts, vendor creation and analytics-preset administration are not newly granted. Existing master data can be selected; ordinary purchasing product creation has a dedicated role. The full native product form can expose options requiring additional roles.
- Native permissions are checked on save; some standard action buttons or list editing controls may be visible before a role/state denial. They must be checked in browser acceptance, including all custom inherited views.
- Installed services/assets may assume an internal session. The supplied source can be checked statically, but only an actual staging boot can validate the full Enterprise and custom-addon stack.

Do not deploy this candidate as an already-tested replacement for every internal purchasing/accounting/stock/signature capability.

## Install / upgrade on staging

1. Commit the single `absar_portal_purchase_monitor` folder to the custom-addons repository branch connected to staging. Replace the existing folder with that technical name. EPS itself is unchanged.
2. Allow the Odoo.sh build to finish. Upgrade **ABSAR Portal Purchase Workspace** in Apps; copying files without a module upgrade is insufficient. Verify version `18.0.1.4.1` and the `project_purchase` dependency.
3. Use designated employee Portal test accounts. Assign **Purchase - Native Workspace Access** plus Prepare, Approve, Monitor or Confirm as appropriate. Product creation additionally needs Prepare and Create Products. Keep Portal selected as the user type.
4. Reload browser assets and open `/my/employee/purchase`. The installed current version having no portal PO page is expected before this addon is installed.
5. Complete the acceptance checks below. Back up the staging database and retain the previous addon revision before upgrading. Removing Native Workspace Access removes the new native ACL entry point; role assignments are not migrated automatically.

Upgrade migration `18.0.1.3.0` is retained for databases upgrading from older versions: it maps compatible legacy projects only into empty real project fields, preserves existing project values and requires resubmission when a legacy approval has no recorded independent approver. An existing 1.3 installation does not rerun that migration.

## Validation included

Performed locally:

- Python compilation; XML, manifest/asset-path and expression parsing; native Purchase/Product/EPS inheritance XPath checks; retained record/template XML IDs; ZIP integrity.
- Native JavaScript syntax check; 58 view-compatibility regression checks in `tools/check_native_views.py`.
- `tools/check_native.py`: 1,279 isolated role/company/ownership scope, bootstrap encoding and opt-in ACL checks.
- `tools/check_logic.py`: 50 inherited isolated validator, approval and financial-allocation checks.

These checks **do not initialize Odoo, render QWeb/OWL in a browser, or execute SQL record rules**. The domain evaluator uses fixtures. They cannot prove installation or runtime compatibility.

Six Odoo integration tests are included in `tests/test_native_security.py` for a database with the EPS/Enterprise dependency stack: Portal identity and explicit opt-in, cross-owner access, direct state/owner injection, approval separation/content immutability, product-role enforcement and the native print transition. **They have not been run here.**

Run on a disposable staging clone with the complete addons path, for example:

```bash
odoo-bin -d STAGING_TEST_CLONE -u absar_portal_purchase_monitor \
  --test-enable --test-tags /absar_portal_purchase_monitor --stop-after-init
```

## Staging acceptance

Use explicit permission before creating/saving test business records. This package has not modified staging data or installed itself there.

1. Fresh installation and upgrade from the installed version complete without missing-model, external-ID, XML-view or asset errors. Confirm users remain Portal users.
2. Open RFQs, Orders, Products and Material Requests with separate Prepare, Review, Monitor and Confirm accounts. Check the actual browser console/network for service startup errors; refresh a nested native action URL and use Back/Forward.
3. Create an RFQ, choose a vendor, change currency/terms/project, add multiple products/sections/notes, change UoM and quantities, select taxes, use Catalog, and check totals/onchanges against the internal form.
4. Test several analytic lines with both configured plans, composite account rows and mandatory-plan errors. Test the native product creation dialog, then select the newly created product on an RFQ. Verify existing products cannot be edited.
5. Open an assigned approved MR and click Create PO. Check the linked MR/project/company defaults. Test a different project, another company, an unapproved MR and No PO Required: reject invalid linking.
6. Save/print/email a draft; upload/remove a quotation attachment; inspect chatter. Submit and review using a different user. Return with a correction note, edit and resubmit. Approve without confirming; confirm only using the separate role. Check configured signing hooks, native double validation and receipt creation.
7. Try direct RPC reads/writes across owners/companies, review-state injection, moving lines, changing template/variant ownership, spoofed context actor/sent flags and unauthorized product creation. Compare visible controls with actual permissions.
8. Open a real confirmed PO with bill/payment/signing extensions. Check every tab, custom field, print report, smart button and wizard against internal behavior. Resolve extension-specific ACLs and approved role scope before claiming complete parity.

The supplied upgrade traceback identifies the numbered product UoM XPath failure corrected in 1.4.1. The corrected package still needs a live staging upgrade and browser acceptance.
