# Optional EPS navigation bridge

Install only where Employee Portal Suite and Portal Backend Workspace are both installed.
The main `portal_backend_workspace` addon does not require this bridge or EPS.
This addon depends on both products and auto-installs when both are present in the addons path.

## Behavior
- Employee-linked portal accounts keep the existing EPS default `/my/employee`.
- `/my/workspace` remains directly accessible to explicitly authorized PBW users.
- A dual-access user gets links to the four allowed workspaces in the EPS sidebar,
  and an Employee Portal link in the PBW sidebar.
- Explicit document links are preserved. `/my/account` remains the standard profile page.
- No operational permission is granted, no group is automatically assigned, and no
  MR/ER, voucher, project, or salary-estimator models are exposed by this navigation bridge.

Business-data integration bridges are deliberately separate work, not included here.
Tested with offline routing and view-inheritance checks against the supplied EPS source;
not installed in a live Odoo database in this build environment.
