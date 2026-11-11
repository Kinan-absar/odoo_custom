# EPS Bridge 18.0.0.9.9 - remove added signatory controls

## Scope
This updates the SAME portal_backend_workspace_eps_bridge addon, starting from
v0.9.8. Main portal_backend_workspace remains at 18.0.0.9.7.

Remove the four additional signatory controls from the portal's new quotation,
saved editable quotation and saved read-only proposal views. The Signatories
expander on a new quotation is removed too. Proposal title and external reference
remain, as do template selection, technical sections and payment milestones.

## Preservation
Only two runtime files differ from the supplied v0.9.8 bridge:
- __manifest__.py: version 18.0.0.9.9.
- views/proposals.xml: remove the signatory entries and disclosure.

Fourteen other runtime files remain byte-identical, including all Python models
and controllers, all JavaScript/CSS, navigation and notification templates. The
existing technical proposal engine/report is not changed or included. No stored
field, database column, value, permission or approval workflow is deleted or reset.
The adapter still preserves stored legacy header values when those input keys are
absent; ordinary portal saves do not clear them. This is a portal UI cleanup, not
a schema or PDF change. The v0.9.8 milestone percentage/HTTP 500 correction remains.

## Executed local checks
- 12 targeted template/source/manifest/preservation checks passed.
- 11 retained percentage-expression tests passed. The older hardcoded v0.9.8
  manifest-version test was excluded and replaced by the v0.9.9 manifest check.
- XML/Python parsing, declared data paths and single-addon ZIP integrity checked.
- Template comparison verifies no markup differences other than the requested
  signatory removal. Original template external IDs/inheritance targets remain.

See validation/signatory_v099/ for tests, logs, the source template and hashes.
Historical test reports/logs are retained but not claimed as rerun.
These are local checks, NOT a live Odoo registry, installation/upgrade, browser
session or PDF test. No live runtime verification was performed.

## Upgrade
Replace the complete existing portal_backend_workspace_eps_bridge folder and
upgrade that same bridge in Apps after deployment/rebuild. Installed version should
be 18.0.0.9.9. Reopen/refresh the quotation afterwards. No main-addon update or
additional bridge is needed. Do not uninstall the existing bridge.
