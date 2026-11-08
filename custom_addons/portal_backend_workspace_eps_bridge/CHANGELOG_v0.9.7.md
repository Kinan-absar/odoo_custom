# 18.0.0.9.7

 original field restored
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

