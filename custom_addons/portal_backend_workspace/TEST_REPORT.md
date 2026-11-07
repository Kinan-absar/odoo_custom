# Executed validation - 18.0.0.9.2

- 21 retained parity regression checks: PASS.
- 10 new shell/asset/layout contract checks: PASS.
- 180 source-based Chromium screen renders: PASS for no JS errors, no visible
  error alerts and no whole-page horizontal overflow.
- 48 tab/dialog interactions: PASS for click/JavaScript execution.
- 16 of 28 adapted original scripts passed. 12 failed or remain incompatible;
  they are NOT counted as passes. Full raw results and the unmodified originals'
  own results are in `validation/`. Some failures are shared with the originals;
  others concern removed custom integrations, renamed/stubbed models, or EPS
  parent-role policies. No live functional conclusion is drawn from them.
- Python/XML parsing, frontend JS syntax and declared local paths are checked
  again during packaging. No live Odoo installation/upgrade was performed.

See LAYOUT_VALIDATION.md for the browser methodology and exclusions. Historical
reports in `validation/` and V09_TEST_REPORT.md are explicitly historical.

Run local static regression suites from this addon directory:

```sh
python validation/check_parity_repairs.py .
python validation/check_layout_contract.py
```

## Remaining live acceptance

The actual Dev asset compiler/QWeb renderer, real company/role combinations,
approval transitions, tax/analytic calculations, receipts/backorders, payroll,
PDF printing, notifications and combined EPS installation must be exercised in
Odoo before treating this as a validated commercial release. Browser fixtures
cannot establish those server-side outcomes.
