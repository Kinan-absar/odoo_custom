# Portal Backend Workspace - Existing EPS Bridge 18.0.0.9.7

This is an UPDATE of `portal_backend_workspace_eps_bridge`, not a new bridge.
Dependencies remain `portal_backend_workspace` and `employee_portal_suite` only.

Shared bell, navigation, permissions and login routing are preserved. The base
addon now owns the original Customer / Client field contract; the bridge no longer
combines two differently stored customer checkboxes.

Construction project read/write adapters and guarded original-Sales confirmation
compatibility remain. When the original Technical & Financial Proposal engine is
installed, the bridge exposes its actual data fields, defaults and PDF report.
The new-quotation screen now includes title/template/reference/signatory controls,
rich sections, include/page-break/order controls and editable payment milestones
before saving. Existing saved proposal controls remain and milestone editing and
native amount displays are added. Native 100% print validation is preserved.

Upgrade `portal_backend_workspace` to 18.0.0.9.7 first, then upgrade this SAME bridge.
Do not install the superseded Sales Data Bridge or uninstall the existing bridge.

Read TEST_REPORT_v0.9.7.md for migration behavior, executed fixture checks and
untested live Odoo steps. This package does not claim live installation or full
four-workspace feature parity.
