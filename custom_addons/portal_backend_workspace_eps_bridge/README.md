# Portal Backend Workspace - Employee Portal Bridge 18.0.0.9.6

One existing addon: portal_backend_workspace_eps_bridge. No third bridge.
Requires the main Portal Backend Workspace v0.9.6 source and Employee Portal Suite.

## Preserved
The shared notification bell, per-user read state, navigation, login routing and
EPS Calls/Messages integration source is unchanged from the supplied merged v0.9.5
bridge. Original customer-flag and construction-project mapping are retained.
No new permissions or role assignments are granted by this upgrade.

## Added here
When the original Technical & Financial Proposal engine is installed, this bridge
exposes its technical document type to PBW, writes/reads the existing type field,
and restores its original portal template, rich-text section, ordering, page-break,
include-in-report, title and payment-milestone controls. PDF uses the installed
original proposal report, not a new replacement layout. Optional model/field
contracts are checked at runtime; missing engines keep standalone behavior.

The bridge does not install or bundle the technical engine, does not redefine its
fields, and does not add any mandatory original Sales/Construction dependency.
It does not add Material Requests, Employee Requests or custom vouchers.

## Upgrade
Deploy both v0.9.6 folders. Upgrade portal_backend_workspace FIRST, then upgrade
this same portal_backend_workspace_eps_bridge addon. Refresh the Sales portal.
Do not uninstall EPS, PBW or this bridge. Ignore the previously superseded separate
portal_backend_workspace_sales_data_bridge ZIP.

Customers must be active, shared or in the user's authorized companies, and have
either Workspace Customer / Client or the original Sales Customer / Client flag.
New quotations use their company-specific customer's company, or the active allowed
company for shared customers. No flags or historical records are bulk rewritten.

See TEST_REPORT.md. Local tests are not evidence of a completed live Odoo upgrade.
Earlier validation/merge_v095 and notifications_v094 files are historical.
