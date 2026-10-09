# ABSAR report suite — Odoo 18

This module carries the final staging report work into the existing ABSAR Odoo database. It includes Invoice, Invoice with Payment, Purchase Order, Quotation / Order, Pro-forma Invoice, Journal Entries, Subcontract Agreement and Subcontractor Payment Certificate.

The purchase, sales, JV and subcontract reports share the final navy design, larger readable fonts, stronger table borders and alternating row backgrounds. PO and project titles are black and bold without an underline; supplier text is 14px; vendor reference, MR and date are shifted right; the stamp is centered at 120px. Signature labels remain “Projects Director” and “Chief Executive Officer”. The invoice versions retain the selected working invoice design and payment block.

The JV uses `wm_journal_entry_report.report_journal_document`, with the existing wrapper `wm_journal_entry_report.report_journal`. It keeps the original five-cell metadata arrangement: Accounting Date / Reference on the left, Journal Type / Company on the right. Its company letterhead repeats on each PDF page. Its own low, borderless footer contains company name at left, page count in the middle and the printing user at right; the company image footer is omitted for JV. The metadata value rules present in the supplied template remain; the JV title underline is removed.

## Install on Odoo.sh

1. Take a full backup of the target database and filestore. Installing this module updates report templates and permanently removes the exact obsolete report records in `data/report_manifest.json`.
2. Extract the `absar_report_suite` folder into the repository's custom addons directory. Keep the module folder name unchanged.
3. Commit it to a staging branch, using a fresh copy of main. Keep the existing ABSAR business modules, Studio fields and `wm_journal_entry_report` installed.
4. After the build, update the Apps list, remove the Apps search filter and install **ABSAR Unified Reports and Cleanup**.
5. Run the print checks below on this fresh copy. Then merge that same tested commit to main and install the module there. Main was not changed when this ZIP was prepared.

For a command-line environment with the required addons paths already configured:

```bash
odoo-bin -d TARGET_DATABASE -i absar_report_suite --stop-after-init
```

Subsequent module updates reapply the same canonical templates and bindings. The module is specific to the existing ABSAR database and stops if required fields or the ABSAR company layout are missing, or if report identities are ambiguous.

## Cleanup and compatibility

`data/report_manifest.json` is the complete, reviewable list of 73 retired template keys, the surplus inactive subcontract wrapper, and the identified obsolete action references. It includes the earlier invoice-copy cleanup and the later PO, quotation, pro-forma and JV cleanup. It does not search for every record containing “copy” and does not purge unrelated reports or Studio history.

Used tax helpers are kept, including `purchase.document_tax_totals_copy_4`, `sale.document_tax_totals_copy_4` and the subcontract helper. Existing action records and XML IDs are reused, preserving existing Invoice and Print PI button references. The old subcontract action is rebound and reused when it is the sole matching action on main, rather than creating another copy. Built-in invoice PDF, PDF Quote and pro-forma actions remain available internally but are unbound from Print menus. The normal RFQ report remains available.

All letterhead, footer and stamp assets are packaged. Templates use module asset XML IDs, never staging attachment numbers or URLs. The header/footer images retain the full pixel resolution embedded in the verified staging printouts; the stamp is the original downloaded PNG.

Before changing report records, installation saves a JSON before-state attachment on this module and records its ID in the configuration parameter `absar_report_suite.last_snapshot_attachment`. If an active template, action button or unlisted inherited view depends on a retired record, installation raises an error and the transaction rolls back. Review and rebind that dependency on the staging copy before retrying. Uninstalling the module is not a rollback for changes to existing records; restore the full database backup to roll back.

## Print acceptance checks

- Print Invoice and Invoice with Payment for an invoice with recorded payments. Check the selected design, QR, amounts, payment lines and amount due.
- Print PO and subcontract; check letterhead/footer, supplier alignment, project/MR/revision, stamp and signature labels.
- Use both the quotation Print button and Print menu. Use Print PI and the pro-forma Print menu. Each should use one header and the same final sales design.
- Print a short JV and a JV of at least two pages. Check the original two-column metadata, debit/credit totals and header/footer on every page.
- Print the subcontractor payment certificate; check its bilingual fields, QR, project and tax calculations.
- Check Print menus and Technical → Reports / Views for the specific retired records. Existing unrelated reports should remain.

## Validation performed for this delivery

The saved staging PO, subcontract, quotation and pro-forma PDFs are one page each, and the long JV is two pages. PO/subcontract totals are SAR 5,252.00; quotation/pro-forma totals are SAR 37,887.90. The long JV totals debit and credit at SAR 2,805,767.57. Both JV pages have the letterhead and the company/page/user footer. Source XML, Python syntax, template calls, packaged assets, exact cleanup scope and action resolution were checked locally.

The new addon has **not been installed in an Odoo runtime or on main**. The container has no Odoo server, and no repository deployment connection was supplied. Validate installation and PDFs on a fresh staging copy using the steps above before the main rollout. The certificate and invoice designs were carried from the saved staging sources; this delivery did not produce fresh PDF tests for those three reports.

The five verified staging PDFs and the second JV page preview are included under `doc/verification`. These are examples of the staging output, not proof of an installation of this addon. The nine offline package and migration-guard checks can be rerun with Python, lxml and Pillow:

```bash
python absar_report_suite/tools/offline_validate.py
```
