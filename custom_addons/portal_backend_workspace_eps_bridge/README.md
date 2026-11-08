# Portal Backend Workspace - Employee Portal Bridge 18.0.0.9.5

This updates the EXISTING `portal_backend_workspace_eps_bridge` addon. It combines
its existing EPS navigation/notification integration with the Sales data adapter.
There is no additional bridge addon to install.

## Required versions

Upgrade `portal_backend_workspace` to **18.0.0.9.5** (the Sales Fixes package) first.
Employee Portal Suite must also be installed. The only declared dependencies remain
`portal_backend_workspace` and `employee_portal_suite`, unchanged from bridge v0.9.4.
The standalone workspace is NOT changed by this package and still works without EPS.

## Preserved from the original bridge

- Shared EPS/workspace notification bell and existing per-user read state.
- Existing access filtering; no new groups, roles or document permissions.
- Cross-portal navigation and login routing, including direct document links.
- Employee-linked dual-access users still land on /my/employee; authorized users can
  navigate to /my/workspace using the workspace links.
- Existing Calls/Messages tools and MR message form behavior.

The controllers, existing models, XML templates and JavaScript for these features
are byte-for-byte unchanged from the supplied v0.9.4 EPS bridge.

## Added to THIS bridge: existing Sales data

1. Customer choices accept either the workspace `pbw_is_sales_customer` flag or the
   original `absar_is_sales_customer` flag when it exists and is Boolean.
   Active-contact and company restrictions remain. No mass data update is performed.
2. The workspace reads and saves the existing `construction_project_id` when it
   exists as a Many2one to `project.project`. List display, forms and searches use
   the same field. A pre-existing local `pbw_project_id` is a fallback only when the
   construction field is empty. Saving/clearing a selection clears a stale fallback.
3. The existing narrowly scoped original-Sales confirmation adapter is included.
   PBW role, ownership/independent-review and company checks still apply; the native
   Odoo confirmation action is retained. This is not a complete merger of two
   independently installed approval systems.

The Sales adapter is byte-identical to the supplied v0.9.5 Sales Data Bridge; it is
now imported from this bridge. Missing optional fields retain standalone behavior.
No mandatory dependency on the original Sales addon, Construction Management,
Customer/Vendor Portal, or Internal Transfer has been added. No fields are redefined.
This does not add MR/ER, payment voucher or other transaction integrations.

## Upgrade the existing bridge

1. Keep/install the accepted **Portal Backend Workspace v0.9.5 Sales Fixes** main
   module. This bridge uses provider hooks introduced by that version.
2. Replace the complete `portal_backend_workspace_eps_bridge` folder with the folder
   in this ZIP. Keep that exact technical folder/module name.
3. Restart/rebuild normally for Python changes; upgrade the EXISTING bridge, then
   hard-refresh open portal tabs. Do not uninstall the existing EPS bridge or EPS.
4. Do NOT install `portal_backend_workspace_sales_data_bridge`: its code is included
   here. The previously supplied separate Sales Data Bridge ZIP is superseded.

If the separate Sales Data Bridge was already installed, keep its source available
until it is uninstalled normally in Apps after the combined bridge has been upgraded.
It defines no fields or data records of its own. Do not delete an installed addon's
folder first. Review the uninstall dialog; stop if it proposes removing other apps.
Do not leave two copies of the same addon in different addons paths.

## Verification and limits

See TEST_REPORT.md for checks executed against this exact package. The notification
and Sales suites execute shipped code with controlled fixtures; no real Odoo registry,
database upgrade, mail delivery or live-user browser test is claimed.

With the main addon and this bridge extracted side by side:

    python portal_backend_workspace_eps_bridge/validation/check_notifications_offline.py
    python portal_backend_workspace_eps_bridge/validation/sales_integration/test_sales_fixes.py
    python portal_backend_workspace_eps_bridge/validation/check_merged_bridge.py

Historical v0.9.4 browser artifacts are retained under validation/notifications_v094;
they are historical evidence only, not freshly executed live-site tests.
