# Portal Backend Workspace 18.0.0.9.2 - layout validation

## What was actually wrong

The original four portals rely on the EPS shell's `#wrap` element for fluid
widths and gutter rules. The consolidated shell had changed that element into
an extra-padded `container-fluid` without `id="wrap"`. The original Sales
1250px fallback cap therefore remained active, and the other workspaces picked
up extra side/top padding. The release restores the original wrapper rather
than painting a new design over the workspaces.

The compact-list helper also contained an `export` statement but was loaded as
a classic script. The before fixture reproduced its syntax error; the corrected
shell declares an ES-module script. The desktop density threshold is restored
from 992px to the source's 769px, with print reset and local shell flag.

## Browser comparison

- 30 initial screen states for original source and candidate, at 1440, 820 and
  390 pixels: 180 renders. Zero uncaught JavaScript errors, visible error alerts,
  or whole-page horizontal overflows in the final deterministic fixtures.
- Compared element x/width, padding, font size and grid columns for the shell,
  lists and form surfaces. 87 of 90 source/candidate cases matched these metrics.
  The three differences are the Purchase list at the three viewport sizes:
  the standalone product excludes the EPS Material Request column and allocates
  its remaining nine columns accordingly. It does not render a dummy MR column.
- Input names/types and table headers match the rendered original native forms.
  Allowed differences: the MR lookup on four Purchase editor states and the MR
  Purchase-list column. The quotation Document Type field is again visible;
  its only base option is Standard Quotation, not the external proposal product.
- 12 additional tab/dialog actions on each original and candidate at desktop
  and mobile sizes: 48 interactions. Zero uncaught JavaScript/click errors.
  These cover Sales/Purchase/Accounting analytics dialogs, Purchase tabs,
  Accounting journal/other/attachment/history tabs and HR employee/contract tabs.
- Original four workspace static assets: 31 of 41 files match byte-for-byte
  after technical namespace mapping. Nine have documented namespace/isolation
  or custom-feature separation changes; one EPS MR/ER-only stylesheet is absent.
  `validation/source_asset_comparison.json` records every file.

## Exact boundaries of the evidence

These are local Chromium fixtures built from actual template/CSS/JavaScript
source, not screenshots of the user's Dev database. A small fixture renderer
substitutes QWeb expressions and sample record data. Browser API requests are
mocked; module imports are combined locally, not through Odoo's asset compiler.
Bootstrap and font fallback are held the same for reference and candidate.
Actual Google font loading, server QWeb compilation, ACL/ORM execution, stock,
accounting/payroll calculations, PDF output and notification delivery are NOT
established by these renders. The provided Dev URL could not be reached here.

This is a targeted original-layout restoration with retained original native
workspace code, not a claim that every possible live workflow is validated.

## Install this update

Replace the entire existing `portal_backend_workspace` folder, upgrade that
same addon, and hard-refresh the browser. Do not uninstall or create a second
addon. The EPS navigation bridge can remain as installed. No native field,
permission group, stored data or bridge identifier is renamed in this update.

## Existing deliberate standalone boundaries

MR/ER, external customer/vendor submissions, custom vouchers/payment plans,
construction IPCs, specialized technical proposals/signing and EPS salary-report
integrations are not recreated in the independent base. They remain bridge
work, as agreed. Standard native quotation/order, receiving, bill/invoice/journal
and employee/attendance/contract/work-entry/payroll functionality is retained.
