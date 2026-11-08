# EPS Bridge 18.0.0.9.5 - combined bridge verification

## Delivered change

One addon: `portal_backend_workspace_eps_bridge`.

The accepted main module `portal_backend_workspace` v0.9.5 is unchanged.
The existing EPS bridge v0.9.4 now includes the Sales data adapter from the
previously separate Sales Data Bridge v0.9.5. No second bridge is required.

## Runtime delta

- `__manifest__.py`: version raised to 18.0.0.9.5; summary updated.
- `models/__init__.py`: imports `sales_data` alongside `users` and `notifications`.
- `models/sales_data.py`: added, byte-for-byte from the supplied Sales data bridge.
- Eight other runtime files from the EPS bridge are byte-for-byte unchanged,
  including its routing controller, notifications/users models, XML and JavaScript.
- Only declared dependencies: `portal_backend_workspace`, `employee_portal_suite`.
- No additional addon, new field, ACL, migration script, or bulk data-copy job.
- No new mandatory original Sales, Construction or Customer/Vendor Portal dependency.

## Executed checks against this combined bridge

| Suite | Result | Scope |
|---|---|---|
| Original notification suite | 41 passed | Shipped notification methods under controlled ORM fixtures: shared bell, recipient scope, duplicate protection, read state and HR events |
| Original Sales v0.9.5 suite, targeted at the merged adapter | 64 passed | Shipped Sales methods: role/creator checks, customer flags, project fallback/save/clear, optional-field absence and guarded original-Sales confirmation |
| Merge/package and routing suite | 16 passed | Preserved-source hashes, declared dependencies/assets/imports, provider hooks, no added schema/ACL, and default/deep-link/profile route decisions |

**121 offline checks passed.** These are not 121 live Odoo tests.

Sales test adaptation is limited to its paths and its manifest expectation: the
combined bridge intentionally depends on EPS as well as the workspace, unlike the
superseded standalone data bridge. No Sales behavior assertions were removed.

The new local asset-file check initially failed because it treated the existing
`?v=18.0.0.9.4` cache query as part of the filename. That test was corrected to inspect
the parsed URL path; the shipped asset and its URL were not changed.

All shipped Python and XML files parsed; JavaScript syntax check passed. Declared
asset/data files exist. The ZIP was checked for corruption, unsafe paths, bytecode
and extra addon roots. The input ZIPs, including the accepted main v0.9.5 ZIP, are
unchanged. Current logs are in `validation/merge_v095/`; provenance/hashes are in
`validation/merge_sources.json` and `SHA256SUMS.json`.

## Not executed or claimed

No real Odoo registry, module installation/upgrade, database migration, live browser,
mail or cross-user notification delivery was executed. The historical notification
browser results shipped under `validation/notifications_v094` were not rerun here.
No full four-workspace feature-parity claim is made by this narrow bridge merge.

## Upgrade

Use the accepted main module v0.9.5. Replace the existing
`portal_backend_workspace_eps_bridge` folder, restart/rebuild for the changed Python
imports, and upgrade that SAME bridge. Hard-refresh portal tabs. Do not install the
separate Sales Data Bridge. Existing groups, read state and route identifiers are
retained; no bridge uninstall is needed for the normal upgrade.

If the separate Sales Data Bridge was already installed, upgrade this combined
bridge first, then remove the now-redundant separate addon through the normal Apps
uninstall flow before deleting its source. See README.md for the safe ordering.

Odoo 18 manifest reference checked for dependency/auto-install semantics:
https://www.odoo.com/documentation/18.0/developer/reference/backend/module.html
