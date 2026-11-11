# Portal Backend Workspace 18.0.0.9.3 - menu cleanup

Base: 18.0.0.9.2 (Original Layout Fix).

## Change
Remove the redundant Settings > Portal Backend Workspace > Workspace Users
navigation by archiving exactly its two menu records on install and upgrade:
- portal_backend_workspace.menu_workspace_users
- portal_backend_workspace.menu_workspace_config

The existing XML identifiers and window action are retained for upgrade
compatibility, but neither menu is visible. No user is deleted or archived.
Workspace permission groups remain managed through the normal Odoo user form.

All Sales, Purchase, Accounting and HR controllers, models, templates, fields,
styles, scripts, security groups and access rights are byte-identical to v0.9.2.
The employee Related User view, portal routing and EPS bridge are unchanged.

## Apply
Replace the existing portal_backend_workspace folder with the folder in this ZIP.
Upgrade the same module in Apps, then reload the Odoo web client. Do not uninstall.
No bridge upgrade or user-permission reassignment is required by this patch.

## Checks performed for this patch
- Source and output ZIP integrity.
- Python AST parsing and XML well-formedness across the addon.
- Manifest data and asset paths exist.
- Fresh-install and upgrade menu-declaration simulation, including repeat upgrade.
- Exactly two existing files changed: manifest version and workspace_settings.xml.
- Every other original file matches v0.9.2 byte for byte.

No running Odoo installation or browser verification was performed for this patch.
Earlier validation reports belong to their stated release and are not new results.
