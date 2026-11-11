# Portal Backend Workspace UI update 18.0.0.9.10

Current update: Accounting-style home tiles, notification-history menu cleanup,
and separate arrow-style portal switch controls. Use main v0.9.10 and the SAME
EPS bridge v0.9.10 for integrated installations. Upgrade the main addon first,
then the bridge; do not uninstall. Standalone Workspace needs only the main addon.

The business workflows, shared bell and previous proposal/customer fixes are
preserved. See TEST_REPORT_v0.9.10.md for the precise change list and local checks.
A live Odoo install/upgrade has not been run.

---
## Previous release documentation (historical)

# Portal Backend Workspace - Existing EPS Bridge 18.0.0.9.9

## Remove added signatory controls
The extra Authorized Signatory, Signatory Title, Customer Authorized Signatory and
Customer Signatory Title controls no longer appear in the portal's new, saved or
read-only proposal forms. The new-form Signatories section is also removed.

Proposal title/reference, templates, sections, milestones, report actions,
permissions, shared notifications, routing and the v0.9.8 HTTP 500 fix are retained.
No stored data, model field or external proposal PDF template is deleted or changed.

## Upgrade
Keep main portal_backend_workspace at 18.0.0.9.7. Replace this existing bridge
folder, deploy/rebuild, and upgrade portal_backend_workspace_eps_bridge in Apps.
Confirm bridge version 18.0.0.9.9, then reopen/refresh the quotation. Do not uninstall.

See TEST_REPORT_v0.9.9.md and validation/signatory_v099/ for local checks and limits.
No live Odoo installation, browser session or PDF render has been verified here.
Historical reports are historical evidence, not rerun results.
