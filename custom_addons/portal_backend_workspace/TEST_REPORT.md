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

## Checks executed for this release

| Check | Result | Limits |
|---|---:|---|
| Retained Sales ownership/permissions/data suite | 64 passed | Actual methods with controlled ORM fixtures |
| New customer/company/proposal/security suite | 37 passed | Actual methods with controlled ORM fixtures |
| Existing notification/security suite | 41 passed | Controlled ORM fixtures, not delivered notices |
| Retained actual-editor browser checks | 18 passed | Chromium 1440/390, mocked HTTP |
| New dropdown/proposal-editor DOM checks | 40 passed | Shipped QWeb markup via a limited local renderer, actual JS/CSS, mocked HTTP |
| Shared layout contract checks | 10 passed | Static assertions |
| Previous targeted parity checks | 21 passed | Scoped local checks, not full original-module parity |
| Python/XML/JavaScript syntax and manifest paths | Passed | Source parsing/file existence |
| Changed-file and ZIP integrity checks | Passed | Preservation, safe archive paths and single addon roots |

231 focused local checks passed. The fixture renderer is NOT Odoo QWeb and these
are NOT 231 live Odoo transactions. The original Sales fixtures were updated only
for company recordset .ids, the intended allowed-company domain, and the dynamic
Document Type selector. Permission-denial assertions were retained. New cases cover
unassigned website companies, foreign/archived/unflagged contacts, missing proposal
engines, invalid/cross-company templates and foreign/duplicate section IDs.
Historical v0.9.x reports and test scripts remain historical evidence; previous
full-suite limitations are not erased by this targeted release.

## Not executed
No live Odoo registry load, installation/upgrade, real-user browser session, native
pricing/tax computation, procurement, report PDF generation, or notification
transport was executed. Database-specific customer checkbox values and installed
module versions could not be inspected. Full parity of all four original modules
is not claimed by this focused patch.

## Upgrade
Deploy BOTH folders using their unchanged technical names. Upgrade
portal_backend_workspace first, then portal_backend_workspace_eps_bridge, and
hard-refresh/reopen the Sales page. The manifest version for both is 18.0.0.9.6.
Do not uninstall either product, mark all contacts as customers, copy checkbox
values, or install the superseded separate Sales Data Bridge.

On this user's integrated database, the original Customer / Client checkbox should
qualify a shared/allowed-company active contact. The technical option is expected
only when the original Technical Proposal engine is installed. If the selector
remains empty, the new inline message identifies the recognized flags; this is
more useful than assuming every empty selector has the same root cause.

Official implementation reference consulted: Odoo 18 ORM API
https://www.odoo.com/documentation/18.0/developer/reference/backend/orm.html
