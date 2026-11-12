# Portal Backend Workspace and existing EPS Bridge 18.0.0.9.6

## Scope
A targeted Sales selector/proposal correction built from the supplied main v0.9.5
and the already-merged EPS bridge v0.9.5. It does NOT introduce a third addon.
The user screenshots show an empty customer dropdown and only Standard Quotation.
There is no access to the user's live contact records, registry or installed-version
state; the screenshots alone do not prove why a particular contact was excluded.

## Confirmed source issues and changes

1. Customer lookup in main v0.9.5 narrowed contacts to user.company_id. The original
   Sales module searched the user's allowed companies. Initial options and Search
   More now use that allowed-company scope through the same domain provider. Active
   contacts must still have the explicit workspace flag, or the original Sales
   flag accepted by the existing bridge. No unflagged/customer_rank fallback.
2. Creation now selects an authorized company consistently: a company-specific
   customer uses its own company; a shared customer uses the active request
   company, falling back to the user's authorized default if the website company
   is not assigned. Arbitrary browser-supplied company IDs are not accepted.
   Project selection and search validate company/customer compatibility. Product,
   account, tax and analytic validation remains company-scoped. Preview responses
   update the displayed currency/company. The form explains an empty selector and
   names the customer flags actually recognized by its installed provider.
3. Document Type was hard-coded to Standard Quotation in both XML and server-side
   create validation. Main now has native-independent document-provider hooks.
4. The EXISTING EPS bridge now adapts the original installed Technical & Financial
   Proposal engine. It detects the known model/field contract before exposing the
   technical option, saves the real absar_proposal_type, and reads the actual saved
   document type instead of displaying a constant Standard Quotation label.
5. Original saved-proposal template selection/load, title editing, rich-text
   sections, positions/reordering, include/page-break flags, and payment milestones
   are restored through that same bridge. Markup comes from the original Sales
   18.0.1.4.14 module, with PBW routes and CSS namespace. Native proposal fields are
   not copied or redefined. The original installed report is used for proposal PDFs;
   payment percentages and current print permissions are checked.
6. Mutations require the existing PBW role/record/company checks and editing
   permission before and after the parent lock. Child IDs are restricted to their
   own quotation, HTML stays in the existing sanitized HTML field, and parent
   One2many commands preserve content-review invalidation. Child write versions
   also participate in line-editor stale-save detection. Standard quotation
   printing, ownership restrictions and own-quotation Approver confirmation remain.

## No-engine behavior
Main still works without EPS or the original proposal addon. In that case only
Standard Quotation is offered. Installing this bridge does NOT install the original
proposal engine. A technical option without its corresponding engine is rejected
on the server, not offered as a non-working dropdown item. The bridge's only declared
dependencies remain portal_backend_workspace and employee_portal_suite.

## Source preservation
Purchase, Accounting, HR, all stylesheets, the main notification implementation,
workspace shell/layout, and the existing bridge's notifications, navigation and
login routing files are byte-for-byte unchanged from the supplied v0.9.5 inputs.
Sales changed only in its provider/controller/template/JavaScript files plus the
main manifest. Existing groups, flags and historical records are not bulk rewritten.

