# Validation - 18.0.0.9.1

Tests below were executed for this build. Historical v0.9 claims are archived in
V09_TEST_REPORT.md and are not counted as fresh evidence.

- 21 targeted actual-source regression checks: PASS (AST/mocked-method and static checks).
- All 27 frontend JavaScript files: syntax PASS.
- All addon Python and XML: parse PASS.
- Declared data and asset files: exist; declared internal XML references resolve statically.
- Isolated Chromium Accounting dialog comparison: original and repaired computed
  styles match at 1280px and 390px; the v0.9 root-class regression is reproduced
  at both sizes. This is NOT an Odoo-hosted page or full UI screenshot comparison.
- 28 original standalone fixture scripts attempted after namespacing/path adapters:
  16 PASS, 12 FAILED or incompatible and NOT counted as passes. Details follow.
- No running Odoo registry/database, live upgrade, actual payroll/tax/stock engine,
  mail delivery or real PDF rendering was tested.

## Original fixture results

| Workspace | Script | Result / qualification |
|---|---|---|
| sales | `check_frontend.mjs` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| sales | `check_print_approval.py` | FAILED / not validated: Original harness also fails against the unmodified original: its fake row omits the current _can_print_for helper. |
| sales | `check_sales_grid.mjs` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| sales | `check_sales_lines.py` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| sales | `check_sales_review.py` | FAILED / not validated: Original harness also fails against the unmodified original: it expects approver edits to invalidate review; current original explicitly permits approver edits. |
| purchase | `check_approver_ui.py` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| purchase | `check_frontend.mjs` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| purchase | `check_grid_ui.mjs` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| purchase | `check_logic.py` | FAILED / not validated: Harness expects the excluded custom amount_paid / payment-voucher metric. Native billed/due/settled calculations differ from that custom metric. |
| purchase | `check_patch.py` | FAILED / not validated: Harness includes Material Request lookups; this base intentionally has no EPS request model. |
| purchase | `check_portal.py` | FAILED / not validated: Multi-addon packaging assertion expects the original manifest in each component, not a consolidated addon. |
| purchase | `check_product_update.py` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| purchase | `check_purchase_policy.py` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| purchase | `check_receipts.py` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| accounting | `check_journal_columns.py` | FAILED / not validated: Original harness also fails against the unmodified original: its fake _journal method does not accept the current kind keyword. |
| accounting | `check_notifications.py` | FAILED / not validated: Harness expects EPS Attendance-Only exclusion and does not model the new independent notification emitter. Independent PBW role policy needs a separate complete fixture. |
| accounting | `check_print_access.py` | FAILED / not validated: Harness models the old external custom JV report lookup; the standalone report uses an independent report reference. |
| accounting | `check_products.py` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| accounting | `check_submission_review.py` | FAILED / not validated: Harness still addresses the old helper name, which has been namespaced for consolidation; this complete script was not successfully adapted. |
| accounting | `frontend.mjs` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| accounting | `grid_frontend.mjs` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| hr | `check_attendance_timesheet.py` | FAILED / not validated: Most native cases pass; original EPS parent-role/Attendance-Only checks and the per-addon manifest assertion are not valid for the independent product. |
| hr | `check_batch_ui.mjs` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| hr | `check_contract_selector.mjs` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| hr | `check_form_ui.mjs` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| hr | `check_frontend.mjs` | PASS; isolated source/DOM/ORM-shaped fixture, not a live Odoo workflow. |
| hr | `check_gateway.py` | FAILED / not validated: 29 of 31 individual tests pass. Remaining cases target the EPS parent-role matrix and excluded EPS salary report scope. |
| hr | `check_print.py` | FAILED / not validated: Harness contains the excluded EPS salary report endpoint and old company report-field stubs. Full current print path remains unverified. |

The adapter changes technical namespaces, URL paths, data attributes, and template
IDs. One expected Accounting error message was updated to match the current
original source; the no-network-request and validation assertions were retained.
No failing assertion is silently counted as a pass. Some old original harnesses
also fail on the original modules; those results are recorded separately.

## Re-run the targeted regression suite

Install Python with lxml, then run from the addon directory:

```sh
python validation/check_parity_repairs.py .
```

The archived fixture logs and reference adapters explain the separate original
fixture run. They need the original source modules and audit folder layout to
reproduce; they are not installation dependencies or Odoo test registrations.

## Remaining acceptance tests

Install/upgrade in the actual Dev database; render every original screen; compare
all editable/read-only roles, company boundaries, multi-stage approval transitions,
partial receipt/backorder quantities, taxes/analytics, payroll results, QWeb PDF
reports, notifications and dual-product coexistence. This update does not assert
that complete source-to-source or live functional parity is established.
