# Portal Backend Workspace - Existing EPS Bridge 18.0.0.9.8

## Saved technical proposal HTTP 500 hotfix
This updates the existing `portal_backend_workspace_eps_bridge` addon. It is not
another bridge. The main `portal_backend_workspace` stays at 18.0.0.9.7.

The failing template is provided by `views/proposals.xml`, which inherits
`portal_backend_workspace.sales__document_detail_extra`. Its milestone total now
formats only the numeric value and emits the percent sign as literal markup.
There is no escaped percent pair in that output expression, so the displayed
percentage is not vulnerable to double-percent normalization during view loading.

## Upgrade
1. Replace the existing `portal_backend_workspace_eps_bridge` folder with this one.
2. Deploy/rebuild using your existing process, then upgrade this SAME addon in Apps.
3. Confirm the bridge's installed version is 18.0.0.9.8.
4. Reopen the saved quotation, including `/my/workspace/sales/513`.

Do not uninstall either addon. A browser refresh alone does not reload the XML view.
No customer data, quotations, security groups, schemas or records are rewritten.
The original template external ID is retained so a normal module upgrade updates it.

Only the runtime proposal total markup and manifest version have changed. Existing
customer/project adapters, new/saved proposal editors, notifications, routing,
permissions, reports, and CSS/JavaScript are otherwise byte-identical to v0.9.7.

See TEST_REPORT_v0.9.8.md and validation/qweb_v098/ for checks and limitations.
Historical reports are retained as historical evidence, not current test results.
