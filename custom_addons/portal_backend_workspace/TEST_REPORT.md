# Portal Backend Workspace 18.0.0.9.5 - Sales corrections

## Files and scope

Base: portal_backend_workspace, upgraded from the uploaded 18.0.0.9.4 package.
Optional companion: portal_backend_workspace_sales_data_bridge 18.0.0.9.5.
The EPS notification/navigation bridge is unchanged and stays at 18.0.0.9.4.

## Confirmed source causes

1. The old can_submit check treated All Company Documents as an ownership override.
   The server submission method repeated that exception.
2. The line-save API enrolled a native quotation under the editor's UID. This could
   turn an unrelated all-documents editor into the stored preparer.
3. Approver implies Prepare, while the old confirmation guard prohibited all managed
   quotations from native confirmation without independent conversion review.
4. The standalone customer selector read pbw_is_sales_customer only. The original
   published Sales module uses absar_is_sales_customer, with the same old UI label.
5. The workspace read pbw_project_id. The supplied backend screenshot shows
   construction_project_id, which the original Construction addon actually defines.

## Implemented behavior

- Ownership comes from the original create_uid, not salesperson, last editor or
  stale preparer-enrollment metadata. All-documents users may still access/edit
  permitted drafts, but can submit/request conversion only for their own quotations.
- An active, company-authorized Sales Approver can directly confirm their own draft
  or sent quotation. An unlinked portal account is denied. Preparers still submit;
  other people's submitted quotations still require independent review.
- The portal action, model method and native PBW button enforce the same checks.
  Native action_confirm remains the business operation. Empty/nonpositive lines,
  native validation failures, cross-company operations, forged approval metadata,
  raw portal RPC and repeated confirmation are tested rejection paths.
- Directly Confirmed has its own audit marker and author; it is not fabricated as
  an independent approval. Unsaved header/line edits disable the confirmation button.
- Initial customer options, Search More and validation use one active/company-scoped
  provider. Without a bridge, the explicit Workspace Customer / Client flag applies.
  With the Sales Data Bridge, the original Sales flag also qualifies a customer.
- With that bridge, project display/selection/search/save use the actual construction
  field. Existing PBW-only selections survive as a fallback when that field is empty.
  Explicitly saving/clearing does not leave a stale fallback that reappears later.
- The data bridge has no mandatory custom dependency other than the workspace. It
  inspects only known field names/types. Missing integrations retain standalone mode.
- If the original Sales guard is installed, only authorized PBW confirmation calls
  receive its private guard context; native business validation is not skipped.
  This is NOT a complete bidirectional merger of two independent approval workflows.

## Executed checks

| Check | Result | Limits |
| --- | --- | --- |
| Targeted Sales policy/controller/data tests | 64 passed | Actual shipped Python methods with controlled ORM fixtures; not an Odoo registry |
| Chromium editor interactions | 18 passed | Actual shipped editor at 1440/390px; mocked save/preview HTTP; not live Odoo |
| Retained narrow parity tests | 21 passed | Earlier controls/role/style contracts, with customer-domain test updated for the provider hook |
| Retained layout contract tests | 10 passed | Original layout/CSS contracts remain |
| Source preservation | Passed | Purchase, Accounting, HR, common shell/bell assets and generic notification model byte-identical to v0.9.4 |
| Python, XML, JavaScript syntax; manifest paths | Passed | Source/schema syntax and file presence only |

**113 targeted local checks passed.** Six optional real-registry tests were added
under tests/test_sales_policy.py but were NOT executed. The original guard snippets
were executed in both inheritance orders for the PBW-initiated own-confirm action;
this does not prove complete coexistence of all native buttons from both products.

## Not tested / not claimed

No live Odoo installation/upgrade, database schema load, stock procurement, invoice
creation, tax engine, mail delivery or real-user workflow was run. This patch does
not constitute a fresh full-parity validation of all four original workspaces. The
previous documented custom-integration exclusions and historical test limitations
remain in the package. Browser fixtures are local tests, not screenshots of the
user's website and not replacements for the product interface.

## Install and focused Dev acceptance

Replace and upgrade the base addon first. Then install Sales Data Bridge on the
shown database to connect its original customer flag and construction project.
Keep the existing EPS bridge installed; it does not need updating for these fixes.
Refresh the portal after the build/upgrade.

- As All Company Documents, open/save someone else's draft: no Submit or conversion
  request should become available. Verify the original creator is unchanged.
- As an Approver, create/save a quotation with valid lines: Confirm Sales Order
  should be available without submission; it must not confirm someone else's draft.
- As a Preparer, select an existing originally flagged customer after bridge install.
- Check an existing construction-linked quotation in the list, detail and search;
  save a changed project and verify the same backend construction field is updated.

Changed runtime source files are recorded in validation/sales_v095/packaging_checks.json
and CHANGES_FROM_V094.patch. No user role memberships are bulk assigned or removed,
and no historical customer/project data is bulk rewritten.
