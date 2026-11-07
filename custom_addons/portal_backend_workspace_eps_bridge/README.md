# Portal Backend Workspace - optional EPS bridge 18.0.0.9.4

Use only where both Employee Portal Suite and Portal Backend Workspace are installed.
The base addon remains independent. This bridge auto-installs when both declared
parent modules are installed and the bridge is available in the addons path.

## Shared bell
The existing EPS bell is replaced, not supplemented with a second bell. The shared
component shows the signed-in user's authorized unread PBW events together with the
original EPS notification categories in both portal interfaces. No EPS event is
copied into PBW, and no new group/document permissions are granted.

PBW events use the same persistent read state in both portals. Opening or marking a
PBW alert read does not approve its business document or clear an outstanding task.
EPS category links keep EPS's original read/visit semantics. Mark workspace updates
read does not clear EPS items. Polling runs every 20 seconds while the page is visible
and on focus/bell opening. Invalidation signals help other open tabs refresh.

Existing EPS Calls/Messages header tools and MR message form submit behavior are
retained. No Employee Portal Suite source files need changing. This bridge does not
add browser/OS push, email delivery or new HR approval workflows.

## Navigation (unchanged)
- Employee-linked portal accounts keep the EPS default /my/employee.
- /my/workspace remains accessible to explicitly authorized workspace users.
- Dual-access users get permitted workspace links in EPS and an Employee Portal
  link in PBW. Explicit document links remain intact.
- The bridge does not grant workspace roles or expose MR/ER, custom vouchers,
  project or salary-estimator models through the standalone workspace.

## Upgrade
Replace/upgrade portal_backend_workspace to 18.0.0.9.4 first, then replace/upgrade
this bridge to 18.0.0.9.4. Hard-refresh existing tabs. Do not uninstall either product.
An EPS-only user should see no PBW entries without workspace access; recipients must
already have access to the underlying company and document.

## Validation
See TEST_REPORT.md. Local source/browser/permission fixtures passed. Real Odoo
installation and cross-user event delivery were not executed in this environment.
With both addons extracted side-by-side, the 41-test offline suite can be run using:

    python portal_backend_workspace_eps_bridge/validation/check_notifications_offline.py

This suite substitutes the ORM; it is not a live Odoo integration test.
