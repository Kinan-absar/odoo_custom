# Portal Backend Workspace + existing EPS Bridge 18.0.0.9.7

## Scope
This corrects the replaced Customer / Client checkbox and extends the technical
proposal controls in the SAME main addon and the SAME EPS bridge. There is no
additional addon and no new custom dependency. The input is the two supplied
v0.9.6 ZIPs, not a rewrite or a simplified replacement workspace.

## Customer / Client: original field restored
- The original stored `res.partner.absar_is_sales_customer` field is used by the
  visible Customer / Client control, initial Sales choices, Search More and server
  validation. It is declared in PBW itself, so this contract also exists without
  the older Sales addon. There is no second customer-flag requirement.
- The Contacts view uses the original technical field, not just a renamed label
  on `pbw_is_sales_customer`. If the original Sales addon also contributes the
  original widget, PBW removes only its own duplicate widget from the generated
  form, preserving the original view and its checkbox.
- A versioned pre-upgrade script preserves the original column EXACTLY when it
  already exists, including False values. It never ORs historical workspace flags
  over the user's original customer classifications.
- ONLY when that original column did not exist, the upgrade restores it using
  existing standalone PBW flag values. The obsolete PBW column is retained,
  hidden/read-only, for data preservation; it is not a second source of eligibility.
- Archived and unauthorized-company contacts remain excluded. No customer_rank
  fallback, no marking every contact, and no blanket data reset is introduced.
- Previously deleted values cannot be recovered from a column that no longer
  exists. This migration preserves available data; it is not backup restoration.

## Technical proposal controls
The original Technical & Financial Proposal addon must already be installed for
these optional functions. The existing EPS bridge connects to its actual models,
fields, defaults and PDF report; it does not install or copy that business engine.

### New quotation, before the first Save Draft
Selecting Technical & Financial Proposal now reveals:
- Proposal title, original template selector/load action, external reference and
  a collapsible signatory section for the engine's available signatory fields.
- Technical sections with section types, titles, rich HTML content, font sizes,
  bold/italic/underline, bullet/numbered lists, order controls, add/remove,
  Include in PDF and New PDF page.
- Editable payment milestones, percentages, due conditions, ordering, removal,
  displayed VAT-exclusive amounts and percentage totals.

Template preview is an authenticated, company-scoped, CSRF-protected read route.
It does not create quotations or child records. The engine's original section
onchange provides default confirmation text. Replacing entered draft content
requires explicit in-page confirmation. A changed customer during an asynchronous
template load invalidates that response rather than overwriting the new draft.

Save Draft submits header, quotation lines, sections and milestones in the existing
creation transaction. Child content is NOT sent on pricing/product lookup calls.
The server accepts only whitelisted new child fields, rejects foreign IDs, unknown
keys, invalid percentages, excessive payloads and unavailable templates, and uses
the original sanitized HTML fields. User-edited template content is not overwritten
by an automatic template reload after creating the quotation.

### Saved proposals
- Existing section/template/PDF routes and controls remain.
- Existing proposal title/reference/signatory fields can be edited with Save Draft;
  read-only users still see the saved metadata.
- The current template is selected in its selector.
- Milestones can be edited and repositioned, not only removed/re-added. Their native
  amount and percentage totals are shown. Updates verify the parent authorization,
  lock/recheck the order and restrict children to the selected quotation.
- The existing native requirement to total 100% before printing remains. Drafts
  may be incomplete during editing.

## Unchanged
Purchase, Accounting, HR, existing global/Sales stylesheets, core notification code,
bridge notification/navigation/login routing, group assignments and external report
source are unchanged from v0.9.6. The only additional stylesheet is narrowly scoped
to the added draft proposal editor. Original Sales ownership/direct-confirmation
rules remain. This is not a fresh full-parity audit of all four workspaces.

## Executed verification
| Suite | Result | What was actually run |
| --- | --- | --- |
| Retained Sales policy/data tests | 64 passed | Shipped methods with controlled ORM fixtures; customer expectations adapted from two flags to the original canonical flag |
| New customer/schema/proposal/security tests | 37 passed | Shipped methods and migration SQL-branch fixture; NOT a PostgreSQL migration |
| Retained notification/security tests | 41 passed | Existing shipped notification methods with controlled fixtures |
| Chromium UI assertions | 62 passed | Shipped JS/CSS and QWeb-derived new/saved/read-only forms at 1440px and 390px; HTTP mocked |
| Python/XML/JavaScript parsing, manifest paths, single-root ZIP checks | Passed | Source syntax and packaging |
| Unrelated runtime-source preservation | Passed | Byte comparisons against supplied v0.9.6 ZIPs |

142 Python fixture tests and 62 browser assertions passed (204 targeted checks).
The local template renderer is NOT Odoo QWeb. Screenshots in validation are local
fixtures, not the user's website. The HTML wrapper/Bootstrap subset is a fixture.
An intermediate browser assertion was corrected to compare rich-text content as
text (the browser correctly preserved paragraph markup), and a test locator was
scoped to proposal sections after adding the Signatories disclosure. An ORM fixture
was also corrected to emulate a singleton recordset when testing milestone writes.
No security assertion was removed. Historical validation logs remain historical.

## Not executed / not claimed
No live Odoo install/upgrade, real registry load, actual PostgreSQL migration,
real-user session, native pricing/tax computation, proposal PDF rendering or live
notification transport was executed here. Those outcomes are not inferred from the
fixture tests. The known historical full-module limitations are not erased.

## Upgrade
Deploy both existing directories, preserving their names. Upgrade
`portal_backend_workspace` first, then `portal_backend_workspace_eps_bridge`.
The visible version of each should be `18.0.0.9.7`. Refresh/reopen the Contacts and
Sales pages after upgrading. Do not uninstall either addon or create/re-tick a new
Workspace customer flag. Existing original customer values are the source of truth.

The proposal engine is still optional. Without it only Standard Quotation is
available. The base addon still requires only its existing standard Odoo apps;
the bridge still depends only on PBW and Employee Portal Suite.

## Technical references consulted
- Odoo 18 ORM API: https://www.odoo.com/documentation/18.0/developer/reference/backend/orm.html
- Odoo 18 view records: https://www.odoo.com/documentation/18.0/developer/reference/user_interface/view_records.html
- Odoo 18 upgrade-script convention (English content on localized URL): https://www.odoo.com/documentation/18.0/de/developer/reference/upgrades/upgrade_scripts.html
