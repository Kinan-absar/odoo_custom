# Validation report - Portal Backend Workspace 18.0.0.9.0

## Results

- 27 adapted original frontend/workflow check scripts: PASS.
- 5 original harness entries: not run; explanations below.
- Internal model/XML/action/template references and asset targets: 0 audit findings.
- Actual module/bridge import graph with Odoo and Werkzeug declaration stubs: PASS.
  This does NOT build a real Odoo registry.
- Python AST, XML parsing, JavaScript syntax and top-level CSS parsing: PASS.
- Extracted EPS stylesheet completeness and desktop/mobile selectors: PASS.
- Native-only base dependency list and one base addon manifest: PASS.
- No new generic portal CRUD ACL on sale.order, purchase.order, account.move or
  hr.employee; native business operations are exposed through scoped gateways.
- Permission-specific menu and portal/internal role boundaries: offline PASS.
- POST/CSRF boundaries and explicit deep-link routing: offline PASS.
- Optional EPS sidebar XPath and dual-product login defaults: offline PASS.
- Static Chromium template/layout/mobile drawer fixture: PASS. Uses mock records,
  lightweight QWeb evaluation, inline module CSS and a small Bootstrap substitute;
  not an Odoo-hosted browser session. Font loading and native module asset loading
  are not established by that fixture.

## Individual adapted checks

- accounting/quality_checks/check_journal_columns.py: PASSED
- accounting/quality_checks/check_notifications.py: PASSED
- accounting/quality_checks/check_print_access.py: PASSED
- accounting/quality_checks/check_products.py: PASSED
- accounting/quality_checks/check_submission_review.py: PASSED
- accounting/quality_checks/design_cases.py: NOT_RUN - Fixture definitions only
- accounting/quality_checks/frontend.mjs: PASSED
- accounting/quality_checks/grid_frontend.mjs: PASSED
- accounting/quality_checks/roles_cases.py: NOT_RUN - Requires a live Odoo database
- accounting/quality_checks/runtime_cases.py: NOT_RUN - Requires a live Odoo database
- hr/tests/check_attendance_timesheet.py: PASSED
- hr/tests/check_batch_ui.mjs: PASSED
- hr/tests/check_contract_selector.mjs: PASSED
- hr/tests/check_form_ui.mjs: PASSED
- hr/tests/check_frontend.mjs: PASSED
- hr/tests/check_gateway.py: PASSED
- hr/tests/check_print.py: PASSED
- purchase/tools/check_approver_ui.py: PASSED
- purchase/tools/check_frontend.mjs: PASSED
- purchase/tools/check_grid_ui.mjs: PASSED
- purchase/tools/check_logic.py: PASSED
- purchase/tools/check_patch.py: PASSED
- purchase/tools/check_portal.py: NOT_RUN - Original multi-addon packaging check replaced by consolidated audit
- purchase/tools/check_product_update.py: PASSED
- purchase/tools/check_purchase_policy.py: PASSED
- purchase/tools/check_receipts.py: PASSED
- purchase/tools/odoo_runtime_cases.py: NOT_RUN - Requires a live Odoo database
- sales/tools/check_frontend.mjs: PASSED
- sales/tools/check_print_approval.py: PASSED
- sales/tools/check_sales_grid.mjs: PASSED
- sales/tools/check_sales_lines.py: PASSED
- sales/tools/check_sales_review.py: PASSED

The original checks were adapted for renamed identifiers and routes, independent
roles and the deliberate removal of optional custom integrations. Assertions for
unavailable voucher, salary-estimator and technical-proposal integrations are not
claimed as coverage of those excluded features. Some original tests substitute
recordsets, mail, browser DOM and accounting engines.

## Not verified

A real Odoo installation/update and registry startup; actual PostgreSQL migrations;
real QWeb view inheritance against the deployed native/custom stack; end-to-end
native pricing/tax, receipt/backorder and payroll computation; notification delivery;
real report rendering; true cross-product coexistence in a running database.

Passing offline fixtures does not establish production readiness. The source and
actual files have been consolidated, but those integration checks still require Dev.
