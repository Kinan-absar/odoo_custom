# ABSAR Portal Sales 18.0.1.4.3

The portal Order Lines grid now follows the supplied internal screenshot:
Product, Analytic Distribution, Quantity, UoM, Unit Price, Taxes, Disc.%, Amount.
Description is editable in the row details dialog. Products, sections and notes
can be added, edited and removed; Save Lines persists the complete draft batch.

The dropdown/modal helper is a byte-identical copy of Purchase's purchase_ui.js.
The allocation editor follows Purchase: account chips, combined accounts across
plans, percentages, Add a Line, Remove, Apply and Clear distribution; each used
root plan must total 100%. Sales and Accounting ship identical control/editor
files without adding a runtime dependency on the Purchase workspace addon.
Control CSS is scoped to these adapters.

The new sales line API preserves existing draft/company/ownership restrictions.
It validates selected products, compatible units, sales taxes and analytic
accounts within the quotation company. Save locks the order and its lines,
checks a version covering header and every line, validates before writing,
updates existing lines in place, and rejects foreign/duplicate line IDs.
Native confirmed/submitted/approved documents cannot be edited through this API.
Line analytic changes also invalidate existing review through the existing
sales model guard.

Product selection reads native sale.order.line pseudo-record defaults using
the actual quotation/pricelist/customer/fiscal position context. Live previews
use an unsaved native sale.order with validated line values so tax totals are
computed by Odoo, with no database preview writes. Save/reopen uses native
persisted amounts. Negotiated prices and quantities are preserved when editing
an already selected product's properties. Product forms include sales price,
sales taxes, units, category and company-dependent income account. Updates
lock template/variant rows and check versions, preserve other-company taxes,
and never move an existing product between companies or alter purchasing flags.

Enter/Shift+Enter navigate the visible columns. Enter after product selection
waits for native defaults, and the last editable column can add the next row.
The main review button is disabled while line edits are unsaved. Product and
line forms, lookups and saves remain scoped; portal roles receive no backend
model ACLs. Technical proposal sections, milestones, workflow, print layouts,
roles and Employee Portal Suite are preserved.

Local validation covers Python/XML/JS syntax, actual gateway/validator fixtures,
exact columns and keyboard/focus behavior, async defaults, native preview
response display, versioned save, product update field/scope/version guards,
readonly controls and combined analytic accounts across plans. These tests
substitute ORM/DOM. No live Odoo server, actual browser layout or native
pricing/tax engine execution was tested. Complete staging checks before use.
