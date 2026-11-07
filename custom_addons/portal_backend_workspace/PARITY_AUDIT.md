> Historical v0.9.1 source audit. For this release see LAYOUT_VALIDATION.md and TEST_REPORT.md.

# Portal Backend Workspace - source parity repair 18.0.0.9.1

## Scope and status

This is a repair of the MAIN `portal_backend_workspace` addon, not the EPS bridge.
It retains the migrated original workspaces from v0.9; no generic replacement
screens were introduced. The four original addons were compared against v0.9.
This report separates confirmed migration defects, retained native features and
custom-integration exclusions. Source presence is NOT proof of live workflow parity.

| Source | Version |
|---|---|
| Sales Portal | 18.0.1.4.14 |
| Purchase Portal | 18.0.1.7.4 |
| Accounting Portal | 18.0.1.3.9 |
| HR Administration | 18.0.1.0.17 |
| EPS layout reference | 18.0.1.20.125 |

## Confirmed base-addon defects repaired

| Area | Difference found in v0.9 | Repair in this build |
|---|---|---|
| Accounting dialog design | Six dialogs retained the old `aca` root class while CSS had been renamed | Restored the matching root class without replacing dialog/editor markup. Search, product, details and reason dialogs inherit the original field/button styling again. |
| Accounting navigation | Vendor Credit Notes existed but were omitted from the sidebar | Added the existing refund workspace link under the original accounting role gates. |
| Accounting native post action | Handling for native action-window results was lost with custom voucher removal | Restored the native auto-post wizard result exception and rejection of other required native wizards; this does not bypass them. |
| Accounting native warning dialog | Customer Invoice was missing from the warning selection; absent custom vouchers were still listed | Added native customer invoices and removed unavailable voucher kinds. |
| Sales navigation | Combined Creator/Monitor users lost a separate monitoring sidebar entry | Restored separate Sales Workspace/My Quotations, Monitoring, Approvals and Review Updates links according to roles. |
| Sales customer selection | Portal choice was widened to any contact with customer_rank, unlike the original explicit customer flag | Restored the original portal customer-flag filter for initial choices and Search More. No global override of the native backend customer field was added. |
| Purchase approvals design | Preparers-only workspace header condition was removed | Restored source visibility for the normal Purchase header, preserving the original approver screen. |
| Pending work | Attention display used unread count; visiting a list could hide still-pending approvals | Pending Sales/Purchase/Accounting counters use total pending count; review decisions retain unread semantics. |
| Attention design | Original compact EPS attention component was absent | Extracted and namespaced the original attention-card component; no employee request models were included. |
| Sidebar counters | Source navigation had counts not represented in central navigation | Added server-rendered counts and refresh through the existing independent notification endpoint. |
| Mobile create menu | Several existing native create routes were absent from the menu | Added role-gated customer invoice, credit note, journal, attendance, contract, payslip and batch shortcuts. No additional CRUD permissions are granted. |
| HR payroll detail | Conditional display of existing original Studio totals was removed | Restored read-only numeric totals only when those fields exist on the already-authorized native payslip. No custom field or addon is required. |
| HR editing | Empty text/relation fields did not preserve original False semantics | Restored original clearing behavior. |
| HR filters | Payslip-only branch used string membership rather than equality | Corrected the single-kind test. |
| HR printing | Missing native payslip report could produce an unhandled lookup failure | Restored guarded report lookup and a clear missing-report error; report model/type checks remain. |

## Original native functionality present in source (not a new completeness claim)

### Sales
`controllers/sales/portal_sales.py`, `controllers/sales/sales_lines.py`,
`models/sales/sale_order.py`, `views/sales/portal_sales_templates.xml`,
`static/src/sales/js/sales_lines.js` and shared editors contain the original
compact lists, order dates/expiration, customer/project selection, catalogue and
product create/edit, analytic allocations, keyboard line entry, sections/notes,
line ordering, native price/tax preview, draft save, quotation review, conversion
review, return and print permission checks. Review/print original test harnesses
are partly stale even against their own baseline; passing frontend checks is not
proof that native review and printing work end to end.

### Purchase
Original lists, search, record forms, line/product editors, analytics, own/all-company
scope, independent approval, return, partial receipts and PO-to-bill interfaces are
retained in `controllers/purchase`, `models/purchase`, `views/purchase` and
`static/src/purchase`. The migrated receipt, purchase-policy, product-update,
approver-visibility, frontend and grid fixture scripts pass. The original custom
payment amount column is NOT equivalent to native invoice settlement.

### Accounting
Original native invoice/bill/credit-note and journal editors, analytic/tax controls,
preparer/direct-posting/approver roles, journal scoping, reset requests and record
history are retained in `models/accounting/service.py`, `accounting.py`, related
models, controllers and `static/src/accounting`. Native Sales/PO invoice sources
remain. Product and editor fixtures pass; notification, complete submission and
report harnesses are not fully validated for the consolidated architecture.

### HR Administration
Original employees, attendance/timesheet, contracts, work entries, payslips,
input adjustments, native payroll batches and employee-contract selectors remain
in `models/hr`, `controllers/hr`, `views/hr` and `static/src/hr`. Frontend, form,
contract-selector and batch-UI fixtures pass. Payroll calculations and printed
payslip PDFs have not been run in Odoo.

## Original custom features still NOT in the independent base

These exclusions explain part of the differences between the standalone addon and
the original four addons installed with their full supporting stack. They are
not claimed as implemented by this update:

| Area | Excluded integration |
|---|---|
| Sales | Technical/financial proposal document type, proposal templates/sections/milestones and the specialized report/construction integration. |
| Purchase | MR import and MR/ER Admin Control; Customer/Vendor Portal submission review; specialized signing indicators and voucher-backed payment metrics. Native receipts and standard vendor bills are not excluded. |
| Accounting | Custom payment/receipt vouchers, their reconciliation/planned payments/CEO workflows; MR-to-bill and construction IPC invoicing; external custom JV report integration. The base retains its own JV report. |
| HR | EPS salary estimators/reports and export; EPS report-to-payroll transfer; EPS-specific overtime, attendance-exception/project and employee settings. Native payroll/attendance workspaces remain. |

No new custom addon dependency was added. The optional navigation bridge is not
modified and does not implement those transaction integrations. Native Odoo
Payroll is still a declared standard dependency.

## Upgrade and checks in Dev

Replace the complete `portal_backend_workspace` folder with this version, upgrade
the SAME addon, and hard-refresh. Do not overlay stale files from old prototypes.
No role memberships are assigned/removed by this patch. The current bridge may
remain installed; its identifiers and hooks were not renamed.

For the restored original Sales selection, mark intended customer contacts using
the **Customer / Client** checkbox (the module's `pbw_is_sales_customer` flag).
A customer_rank value alone is no longer sufficient, matching the original portal.

Verify the actual detail forms (not only list pages): product/search/detail dialogs,
combined Sales roles, approval counts after visiting lists, Purchase approval header,
credit-note navigation, HR edits and payslip printing. Full end-to-end feature parity
and a live Odoo installation/upgrade remain unverified.

## Files changed from v0.9

- `__manifest__.py`
- `controllers/hr/portal.py`
- `controllers/sales/portal_sales.py`
- `controllers/workspace.py`
- `models/accounting/post_confirmation.py`
- `models/accounting/service.py`
- `models/hr/gateway.py`
- `models/workspace.py`
- `static/src/accounting/accounting.js`
- `static/src/core/workspace_layout.css`
- `static/src/core/workspace_shell.js`
- `views/purchase/portal_workspace_pages.xml`
- `views/workspace_layout.xml`
