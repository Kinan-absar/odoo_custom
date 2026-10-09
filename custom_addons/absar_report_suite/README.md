# ABSAR Unified Reports — 18.0.2.0.0

Rebuilt from the supplied final staging checkpoint. Keep the technical folder name `absar_report_suite`.

## Reports included

- Invoice
- Invoice with Payment
- Purchase Order
- Quotation / Order
- Pro-forma Invoice
- Journal Entries / Journal Voucher
- Subcontractor Payment Certificate
- عقد مقاولة من الباطن / Subcontract Agreement

The saved report designs, navy tables, titles, stamp, and business letterhead/footer are carried forward. JV uses its own company header and borderless footer: company left, page count center, printing user right. The title has no underline; the supplied accounting-date/reference and journal/company information table is preserved.

## Replace the queued installation

1. Replace the entire old `absar_report_suite` folder with the folder inside this ZIP. Do not put the ZIP or an extra version folder inside the addons directory.
2. Commit and push to the staging branch.
3. After the new build is running, open Apps in developer mode, choose Update Apps List, remove the Apps search filter, and search for `absar_report_suite`.
4. If the card shows **Cancel Install**, click it once to cancel the old queued attempt. Then click **Activate** for the replacement. If the module is already installed, choose **Upgrade** instead.
5. A completed installation should show an installed module, not **Cancel Install**. In Module Info, check that the version is `18.0.2.0.0`.
6. Print the eight reports on staging, including a two-page JV, a paid invoice, a quotation and Print PI. Check actual amounts and any project/MR/revision fields.

`to install` means an installation is still pending; a successful Git build alone does not establish that this addon installed. The supplied screenshot does not identify the server-side cause of that pending state. This rebuild removes the custom journal addon/PDF quote builder dependencies and database-specific preflight/deletion pipeline from the old package. It never changes a module's state to pretend installation succeeded.

## Implementation

All templates, three image attachments, two paper formats and eight report actions load through normal Odoo XML data. A small setup function preserves existing report action IDs, rebinds existing Invoice/Print PI and standard sales/purchase buttons, and hides exact obsolete actions from Print menus. Existing report actions are resolved by external ID first and their selected IDs are retained across upgrades. Duplicate names do not abort installation.

Templates use module-owned names and packaged images, without database attachment IDs or a dependency on Studio XML IDs. Optional project, MR and revision fields display when the corresponding business customizations exist. No global company external-layout view is overwritten. Invoice/ZATCA QR and payment data remain derived from the existing records.

The module does not permanently delete historical views or actions. It removes exact obsolete actions from Print menus. Original values of modified existing report actions are saved once in `absar_report_suite.original_report_actions`; the uninstall hook restores those values. This snapshot is for this version's action edits only; it does not reverse changes already made by the previous addon.

## Verification

Local checks passed for Python/XML syntax, template dependencies, assets, fresh action setup, existing action reuse, duplicate actions, standard buttons, repeat setup, preservation of unrelated reports and absence of module-state manipulation. See `doc/validation.json`.

This package has **not been installed in a live Odoo runtime**, and no fresh PDF was rendered from it here. The saved checkpoint supplied the designs; local validation is not proof of live installation or PDF pagination. Odoo integration tests for actual HTML rendering and repeat setup are included under `tests/` and run only when Odoo's test runner is enabled.

Offline checks:

```bash
python absar_report_suite/tools/validate.py
```

Odoo integration tests on a staging environment with all dependency addons present:

```bash
odoo-bin -d STAGING_DATABASE -i absar_report_suite --test-enable --test-tags /absar_report_suite --stop-after-init
```

For an already installed module, use `-u absar_report_suite` in place of `-i`. Use the deployment environment's configured addons paths. Only genuine installation success should result in the `installed` state.
