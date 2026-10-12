# ABSAR Unified Reports — 18.0.2.0.32

Keep the technical folder name `absar_report_suite`. This update fixes the report-action duplication and Purchase Order signing/filename regressions from 18.0.2.0.0–18.0.2.0.1.

## Changes

- Reuses existing report action IDs. A module-owned action is created only when there is no existing compatible action. XML loading no longer creates eight extra actions on each installation.
- Removes unused extra module actions and allowlisted custom duplicates after checking references. Referenced actions remain available to their consumers and are hidden from the Print menu. System-owned actions are preserved. Different system actions such as PDF/PDF without Payment can remain in Technical Reports because internal Odoo buttons use them.
- Preserves the PO action's `purchase.report_purchaseorder` report name. A removable QWeb inheritance bridge routes that standard name to the ABSAR design. Existing Send to Sign callers can render using their original reference.
- Uses the same PO filename structure as the signing title: PO number, supplier, MR, then project, without an added PO/RFQ prefix. A revision suffix is included when present. Optional project/MR fields can be absent. This explicit filename setting replaces older saved expressions so they cannot reintroduce duplicate prefixes or a different field order.
- Keeps the existing report designs, packaged letterhead/footer/stamp and dedicated JV footer.

Reports: Invoice, Invoice with Payment, Purchase Order, Quotation / Order, Pro-forma Invoice and Journal Voucher.

## Upgrade staging

1. Replace the entire existing `custom_addons/absar_report_suite` folder with the folder inside this ZIP.
2. Commit and push to your staging branch, and let the build finish.
3. Upgrade the already installed **ABSAR Unified Reports** module. Do not uninstall it first. Verify version **18.0.2.0.3** in Module Info.
4. Check the Print menu on a PO and invoice: each desired report should appear once.
5. Print a PO containing a supplier, project and MR. Check the downloaded filename and the design/amounts.
6. Use Send to Sign on a suitable staging test PO with the correct workflow. Check the generated title, PO PDF, quotation/MR attachments, and signature positions.
7. Print invoice/payment, quotation/proforma and JV reports as before.

Technical Reports may still contain distinct system actions, or an old custom action referenced by a retained setting/button. The cleanup logs why records are preserved; it does not delete every report with a similar display name.

## Cleanup and restoration

Cleanup considers only retired custom records in `data/integration.json` and the duplicate action IDs discovered during setup. Its dependency graph checks retained report actions, inherited views, QWeb calls, action buttons, menus, stored server actions and stored relations from installed models. Other addon ownership protects a record. Unrelated payroll, attendance and employee reports are outside this scope.

Before deletion, a JSON attachment saves record architectures, action values and external IDs. `absar_report_suite.last_cleanup` stores the latest summary, and `absar_report_suite.last_deletion_cleanup` retains the last nonempty result. These are diagnostic snapshots, not automatic restoration. The uninstall hook restores saved values of surviving pre-existing actions; it does not recreate deleted custom templates/actions. Use a database backup for a full rollback.

Reused pre-existing actions are not given module-owned external ID aliases, so uninstalling this addon does not claim ownership of core/custom actions. Only newly created fallback actions have this module's own external IDs. Existing fallback/reference actions are marked `noupdate` to protect them from Odoo's end-of-upgrade deletion process.

## Verification

Offline checks exercise the actual setup function for fresh/existing-action scenarios, an upgrade with eight module duplicates, repeated setup, replacement of older filename expressions, the actual filename helper, cleanup graph cases, XML/QWeb syntax and packaged assets. They pass; see `doc/validation.json`.

This version has not yet been installed or rendered in a live Odoo runtime. The included Odoo integration tests additionally test the legacy PO report reference, actual PDF rendering/signing-package construction (without sending requests), duplicate cleanup, repeat setup and report HTML rendering.

```bash
python absar_report_suite/tools/validate.py
odoo-bin -d STAGING_DATABASE -u absar_report_suite --test-enable --test-tags /absar_report_suite --stop-after-init
```

Use the deployment's configured addons paths. Main deployment should follow successful staging upgrade and workflow verification.

## Journal voucher redesign — 18.0.2.0.4

English Journal Voucher on the left, voucher number centered, Arabic title on the right. White cards with one subtle outline; no heading frame or inner cell grid. Voucher details include accounting date, reference, company and journal name. Journal lines show account, description, partner, analytic allocation (including percentages and multiple plans), debit and credit. Company-currency precision and original debit/credit totals are retained. Empty partner/analytic values show a dash. Packaged company letterhead and the company/page/printed-by footer are retained.

Only the journal template changes; existing report bindings, cleanup safeguards, PO filenames and other designs remain. Replace the addon and upgrade ABSAR Unified Reports on staging. Check a split analytic allocation, partner values, multi-page entries and batch printing. Local validation passed; live Odoo installation/PDF rendering has not been performed.

## Purchase order redesign — 18.0.2.0.5

PO number on the left; Project: followed by the project name on the right. Untitled supplier card with supplier/address/VAT, vendor reference, MR and order date. White order-item card, thin horizontal separators, unframed heading, readable totals and existing terms. Original Projects Director/Chief Executive Officer labels and company stamp retained. RFQ/cancelled status, revisions, shipping addresses, discounts, packaging, sections and subtotals retained. Existing tax calculations, report bindings, PO filenames and journal redesign are preserved.

Replace the addon and upgrade ABSAR Unified Reports on staging. Print PO 237 and a longer PO, verify totals/discounts/notes, then test Send to Sign and check placeholder placement after the report redesign. The sample fits one page; live Odoo pagination can vary with content and PDF fonts. Live Odoo installation and rendering were not tested.

## Invoice cards — 18.0.2.0.6

Existing bilingual layout retained: centered title, customer left, QR right, English/value/Arabic detail rows and original item columns. Navy text and white rounded cards replace grey/purple fills and inner grids. No added card headings. Existing Invoice and Invoice with Payment report routes retained. QR generation, calculation directives, sections/subtotals, currencies and payment values are unchanged. PO and journal designs retained.

Replace absar_report_suite and upgrade ABSAR Unified Reports on staging. Print both versions of INVAB/2026/068; check QR, bilingual alignment, negative down payment, totals and payment visibility. Check longer invoices for pagination. Local checks passed; live Odoo rendering and installation have not been tested.

## Invoice table alignment — 18.0.2.0.7

Invoice line columns now total 100% with or without discounts. Section, note and subtotal rows span exactly six or seven displayed columns, preventing phantom columns and a blank strip at the right. Bilingual subtotal labels keep currency values in left-to-right order. The invoice grand total uses the same `o_total` styling as the purchase order, including company total color. A4 paper size and existing margins are unchanged. Offline validation passed; verify both invoice variants after upgrading staging.

Payment rows are restored inside the right-hand totals card, directly below Total, only for Invoice with Payment. Invoice tables opt out of Odoo external-layout table decoration so inner frames do not appear inside cards.

## PO table border reset — 18.0.2.0.8

Purchase order tables now also opt out of external-layout table decorations and explicitly suppress their outer table border, outline and shadow. The card outlines and item row separators remain. All invoice fixes from 18.0.2.0.7 are included. No PO fields, tax computations, signature labels, report routing or paper margins changed. Verify actual PDF rendering on staging after upgrade.

## Compact PO from 18.0.2.0.8 — 18.0.2.0.11

Rebuilt directly from the 18.0.2.0.8 ZIP. Supplier card padding and line spacing are reduced; supplier name is 15px beside 13–14px details. Order Items heading removed. Totals have tighter row spacing and a subtle line beneath each row. All other report templates, letterhead/footer, paper formats, report routing and original signature block retain 18.0.2.0.8 behavior. No changes from 18.0.2.0.9 or 18.0.2.0.10 are included. Verify actual staging PDF pagination.

## PO supplier name and VAT only — 18.0.2.0.12

The supplier card shows name and VAT number only. Supplier address and phone are omitted from the printout; Vendor Reference, MR and Order Date remain. Totals underline separators removed; compact spacing and bold Total remain. No stored supplier data changed. Invoice, header, margins and signature layout retain the 18.0.2.0.8 base.

## PO one-row details and teal card outline — 18.0.2.0.13

Supplier, Vendor Reference, MR and Order Date share a row with widths 50%, 19%, 14% and 17%. VAT stays under supplier name. Optional MR behavior and confirmed/draft date logic are unchanged. PO cards use a 0.75px teal outline (#177b83), matching the item header separator color with a thinner stroke. Other reports and business directives are unchanged.

Invisible table borders explicitly use transparent color in PO and invoice. Uploaded PDFs contain zero-area dark edge fills that can appear as hairlines in some viewers. Transparent hidden borders prevent the source from using the dark text color for those fills. Intentional teal header rules and item separators retain their explicit bottom border colors. Actual PDF viewer rendering must be verified after upgrading.

## Visible thin teal PO card outlines — 18.0.2.0.14

PO supplier/details, items, terms and optional shipping cards receive explicit inline 1px solid teal borders. This overrides external layout border resets and avoids subpixel border widths that can disappear in PDF rendering. The item heading separator remains 2px, so card outlines are thinner. Transparent hidden table borders, one-row details, totals and signature layout remain unchanged. Verify actual staging output.

## Matching invoice teal card outlines — 18.0.2.0.15

Both invoice variants now use the same explicit 1px teal card outlines as the approved PO. Customer, QR, invoice details, items, totals and optional note/currency cards are covered. Existing layout, payment display flags, computations, content and transparent hidden table borders remain unchanged. All PO changes are retained.

## Invoice closed outlines and borderless QR — 18.0.2.0.16

QR wrapper no longer uses the card class and explicitly has no border, outline or shadow. Customer, invoice details and items cards use explicit thin teal borders on all four sides, with square corners for consistent PDF edges. Existing content, QR generation, payment flags, totals and PO layout are preserved. Check actual staging output.

## Compact bilingual invoice details — 18.0.2.0.17

The invoice details card has two columns: Invoice No, Invoice Date and Due Date on the left; Source and Payment Reference on the right. Each row retains English label, centered value and Arabic label. Card padding and row spacing are reduced. Optional field logic and all invoice business directives are unchanged. Existing closed teal border and borderless QR are retained; PO unchanged.

## Rounded teal invoice and journal cards — 18.0.2.0.18

Invoice customer, details and items card corners are rounded at 7px. Journal voucher details and entries cards receive matching thin 1px teal outlines and rounded corners. Invoice QR remains borderless. All content, compact invoice detail columns, partner/analytic columns, computations, report routing and PO styling are preserved.

## Tapered rounded teal cards — 18.0.2.0.19

PO, both invoice variants and journal voucher cards use a fuller 3px teal left edge and a thin pale 1px right edge. Top and bottom edges fade from teal to pale using standard and WebKit gradients, with a solid fallback. Corners remain rounded. Card content and existing layout remain intact; invoice QR stays borderless. Actual staging PDF appearance still needs verification.

## Explicit closed tapered card edges — 18.0.2.0.20

Tapered cards render explicit positioned top and bottom edge elements inside each rounded container rather than relying on generated pseudo-elements. This addresses missing top edges shown in the uploaded invoice screenshot. Applies to PO, invoice and journal cards; QR stays borderless. Actual PDF appearance needs staging verification.

## Compact journal voucher details — 18.0.2.0.21

Removed the Voucher Details heading. Accounting Date and Reference share the left column; Company and Journal Type share the right column. Labels and values are aligned side by side in two compact rows with reduced card padding. Long values can wrap. Rounded tapered teal edges remain in place.

Validation: offline suite checks and QWeb directive preservation passed. Fresh staging PDF rendering remains required.


## Smooth single-line teal cards — 18.0.2.0.22

Removed the separate top and bottom gradient strokes that overlapped the rounded outline and caused doubled, uneven-looking corners. Invoice, purchase order and journal voucher cards now use one continuous 1px teal border with a consistent 12px radius. Card content and layout are unchanged; the invoice QR remains borderless.

Validation: offline suite and XML/QWeb checks passed. Fresh staging PDF rendering remains required.


## Teal accent card treatment — 18.0.2.0.23

Invoice, purchase order and journal voucher cards use a 6px deep-teal left accent, a single thin teal outline on the remaining edges, 16px rounded corners and a soft teal shadow. The separate top and bottom strokes remain removed. Report content, layout and the borderless invoice QR are unchanged.

Validation: offline suite and XML/QWeb checks passed. Fresh staging PDF rendering remains required.


## Teal accent cards on remaining commercial reports — 18.0.2.0.24

Quotation and proforma reports share the same teal card styling around customer/order details, lines, totals, terms and optional products. Subcontractor reports use it around supplier/order details, lines, totals and notes. Cards retain a 6px deep-teal left accent, thin teal outline on the other sides, 16px corners and soft teal shadow. Report content and calculations are preserved.

Validation: offline module checks and XML/QWeb parsing passed. Odoo PDF rendering after upgrade remains to be verified.


## Enforced card styling across all ABSAR report outputs — 18.0.2.0.25

The shared report stylesheet now defines the teal card treatment for quotation, proforma, subcontractor and subcontractor payment certificate outputs. The earlier templates carried card classes without the shared declarations, so those reports kept their old appearance. The certificate supplier, summary, line, totals and notes sections now use the same cards. Existing invoice, invoice-with-payment, purchase order and journal voucher card styles remain. The report action setup version is synchronized for upgrade.

Validation: offline suite, XML/QWeb checks and card-selector assertions passed. Odoo PDF rendering after upgrade remains to be verified.


## Sales header and compact project/customer details — 18.0.2.0.26

Sales order, quotation and proforma share a clean two-sided header: document title and number on the left, linked project on the right. The project comes from the standard `sale.order.project_id` field (provided by `sale_project`), replacing the Studio-specific field. Sales titles no longer have an underline. Customer details are reduced to the name and VAT number; reference, date, expiration and all remaining report content are preserved. Purchase orders label the existing PO number with “Purchase Order #”.

Validation: offline suite and XML/QWeb checks passed. Odoo upgrade and PDF rendering remain to be verified.


## Sales, quotation and proforma match the invoice/JV card treatment — 18.0.2.0.27

Sales order, quotation and proforma now use the same compact, white rounded cards with a slim teal accent, navy text, teal table header rule and light row separators used by the invoice and journal voucher. Their document title has no underline and the project remains aligned at the right. Customer details show only name and VAT. References, dates, expiration and remaining report content are preserved. The styling is scoped to these sales reports.

Validation: offline suite, source checks and ZIP integrity passed. Live Odoo PDF rendering remains required.


## Unified headings and invoice-style total cards across routed reports — 18.0.2.0.28

The PO heading now prints “Purchase Order #” and its number on one line, matching the sales heading; RFQs use “Request for Quotation #” with the same alignment and project position. Sales orders, quotations and proformas show the project field on the right. The invoice-style outlined total card is applied to sales, PO/RFQ, subcontract agreement and subcontractor payment certificate totals while each report keeps its existing total labels. The subcontract agreement and RFQ tables now use the open white table with teal header rule, and the payment certificate is brought into the same teal/navy card design. Invoice and journal voucher layouts remain as the visual reference.

Validation: offline suite, source checks and ZIP integrity passed. Live Odoo PDF rendering remains required.


## Correct project field and smooth card borders — 18.0.2.0.31

Sales order, quotation and pro-forma headers now read the actual Odoo project selector on these records (`sale.order.construction_project_id`), not the empty Studio field. They fall back to Odoo linked Projects only on databases without that selector. Purchase, subcontract and sales headings use a shared 18px size, matching the Project label. Cards use a rounded 6px teal left rail with one thin outline on the other edges, avoiding the doubled inset stripe and keeping the intended accent. Nested tables keep clean separators without boxed borders, total text remains visible, and empty subcontract notes no longer render an empty card.

Offline validation passed. The staging Sales Order S00480 form was inspected read-only and confirmed the real project field is `construction_project_id` (value: “Bathroom repair and maintenance Exit 4”); the Studio project field is separate and empty. The report action list was reviewed read-only (102 actions), and RFQ routing is included. Live PDF rendering was not performed.


## Retire subcontract reports and remove sales table frames — 18.0.2.0.32

The unused Subcontract Agreement and Subcontractor Payment Certificate reports are removed from the module templates and their Purchase/Bill Print bindings are retired during upgrade. The regular Purchase Order, invoice and bill reports remain. Sales order, quotation, pro-forma and optional-product description tables now use the same Odoo layout-styling opt-out as the Purchase Order table, so browser layout styles do not draw a second box inside the teal card.

Offline validation checks the retirement behavior, sales table classes, XML/QWeb references and package integrity. Live Odoo installation and PDF rendering still need verification after upgrading the module.


## Explicitly remove sales description grid — 18.0.2.0.33

The sales description and optional-product tables now explicitly clear all outside and vertical cell borders inside their cards, with only the teal header rule and light horizontal row separators retained. This addresses browser styles that remained visible after using the same layout-styling opt-out as the PO.

Offline validation passes. This version has not been installed or rendered live in Odoo.


## Delete obsolete subcontract report actions — 18.0.2.0.34

Upgrade setup now deletes the exact Subcontract Agreement and Subcontractor Payment Certificate report actions, in addition to retiring their report templates. They will no longer remain in Technical Reports after upgrading.

Offline validation passes. The action deletion is covered by the upgrade setup simulation and Odoo integration test; live Odoo upgrade has not been run.


## Contextual accounting print choices — 18.0.2.0.35

Journal Voucher is now the only native account.move Print-menu action. The direct-print dialog defaults to Journal Voucher and shows only Journal Voucher for miscellaneous entries; invoices and vendor bills also retain the unified Invoice PDF option. Older invoice copies, tax-invoice shortcuts, and unrelated reports such as Timesheets are excluded. The duplicate “Print Tax Inv” Studio header button is hidden during report setup. The original report action bindings are saved and restored if the module is uninstalled.

Offline validation and filtering tests pass; staging upgrade and PDF printing must be verified after installing the ZIP.
