# ABSAR Unified Reports — 18.0.2.0.2

Keep the technical folder name `absar_report_suite`. This update fixes the report-action duplication and Purchase Order signing/filename regressions from 18.0.2.0.0–18.0.2.0.1.

## Changes

- Reuses existing report action IDs. A module-owned action is created only when there is no existing compatible action. XML loading no longer creates eight extra actions on each installation.
- Removes unused extra module actions and allowlisted custom duplicates after checking references. Referenced actions remain available to their consumers and are hidden from the Print menu. System-owned actions are preserved. Different system actions such as PDF/PDF without Payment can remain in Technical Reports because internal Odoo buttons use them.
- Preserves the PO action's `purchase.report_purchaseorder` report name. A removable QWeb inheritance bridge routes that standard name to the ABSAR design. Existing Send to Sign callers can render using their original reference.
- Restores the original PO filename expression from the saved before-state when it explicitly includes supplier, project and MR. Otherwise uses the PO number, supplier, project and MR, with an RFQ prefix for draft/sent orders and no duplicate PO prefix. Optional project/MR fields can be absent.
- Keeps the existing report designs, packaged letterhead/footer/stamp and dedicated JV footer.

Reports: Invoice, Invoice with Payment, Purchase Order, Quotation / Order, Pro-forma Invoice, Journal Voucher, Subcontractor Payment Certificate and Subcontract Agreement.

## Upgrade staging

1. Replace the entire existing `custom_addons/absar_report_suite` folder with the folder inside this ZIP.
2. Commit and push to your staging branch, and let the build finish.
3. Upgrade the already installed **ABSAR Unified Reports** module. Do not uninstall it first. Verify version **18.0.2.0.2** in Module Info.
4. Check the Print menu on a PO and invoice: each desired report should appear once.
5. Print a PO containing a supplier, project and MR. Check the downloaded filename and the design/amounts.
6. Use Send to Sign on a suitable staging test PO with the correct workflow. Check the generated title, PO PDF, quotation/MR attachments, and signature positions.
7. Print invoice/payment, quotation/proforma, JV and subcontract reports as before.

Technical Reports may still contain distinct system actions, or an old custom action referenced by a retained setting/button. The cleanup logs why records are preserved; it does not delete every report with a similar display name.

## Cleanup and restoration

Cleanup considers only retired custom records in `data/integration.json` and the duplicate action IDs discovered during setup. Its dependency graph checks retained report actions, inherited views, QWeb calls, action buttons, menus, stored server actions and stored relations from installed models. Other addon ownership protects a record. Unrelated payroll, attendance and employee reports are outside this scope.

Before deletion, a JSON attachment saves record architectures, action values and external IDs. `absar_report_suite.last_cleanup` stores the latest summary, and `absar_report_suite.last_deletion_cleanup` retains the last nonempty result. These are diagnostic snapshots, not automatic restoration. The uninstall hook restores saved values of surviving pre-existing actions; it does not recreate deleted custom templates/actions. Use a database backup for a full rollback.

Reused pre-existing actions are not given module-owned external ID aliases, so uninstalling this addon does not claim ownership of core/custom actions. Only newly created fallback actions have this module's own external IDs. Existing fallback/reference actions are marked `noupdate` to protect them from Odoo's end-of-upgrade deletion process.

## Verification

Offline checks exercise the actual setup function for fresh/existing-action scenarios, an upgrade with eight module duplicates, repeated setup, backup filename restoration, the actual filename helper, cleanup graph cases, XML/QWeb syntax and packaged assets. They pass; see `doc/validation.json`.

This version has not yet been installed or rendered in a live Odoo runtime. The included Odoo integration tests additionally test the legacy PO report reference, actual PDF rendering/signing-package construction (without sending requests), duplicate cleanup, repeat setup and report HTML rendering.

```bash
python absar_report_suite/tools/validate.py
odoo-bin -d STAGING_DATABASE -u absar_report_suite --test-enable --test-tags /absar_report_suite --stop-after-init
```

Use the deployment's configured addons paths. Main deployment should follow successful staging upgrade and workflow verification.
