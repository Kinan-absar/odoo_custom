# ABSAR Universal Send to Sign — Odoo 18

Install this addon alongside ABSAR Sign Workflow Core **18.0.1.0.15 or later**.
Keep the current PO, voucher and construction bridges installed. This addon adds
configurable integrations for other persistent business document models.
It does not add fields or write signature status onto arbitrary source models.

## Configure a document type

1. Sign → Configuration → Universal Signing → New.
2. Choose the model and its QWeb PDF report. Give the integration a name.
3. Optionally choose primary form views. Empty means all current primary forms.
4. Optionally map a project field. Otherwise a conventional project_id is used
   when it refers to project.project.
5. Optionally choose a state field and allowed technical values, e.g. state and
   sale,done for confirmed sales orders. Both settings must be filled or empty.
6. Configure a Signing Workflow for the same model and company. A matching
   project-specific workflow overrides the company default. Select signer users
   and distinct roles, then configure Printed Heading, Saved Position, or Review
   in Template for each step.
7. Activate the integration, then reopen/refresh the document form.

The Send to Sign header button appears for Odoo Sign users. It also has a
form-only Action menu entry. Selecting multiple documents is rejected.
If another module adds a new primary form later, use Refresh Buttons.
Deactivate an integration to remove its generated buttons.

## Sending

By default the first click prepares the report, signature/date pairs, and opens
the template. Use native Send to invite the configured signers in order.
Enable **Send Directly When Placement Is Ready** to send immediately when every
position resolves and no placement issue is reported. Missing or ambiguous
headings, overlaps, and manual-placement steps always open review instead.
The IPC overlapping-heading correction from Core 18.0.1.0.15 is reused.

The signer chain is frozen when a template is prepared. Editing the workflow
later does not silently change the recipients of an existing template. Native
Send rechecks source permissions, company, state, prepared signers, and duplicate
requests. Native Sign Now is not the workflow flow.

Repeated clicks open the existing template/request. Sign → Universal Signing
History contains preparations and links to their source and native Sign request.
New Signing Revision explicitly creates another preparation, retaining history.
An active request must be finished or cancelled in Odoo Sign first; superseded
unsent templates cannot subsequently be sent. Prepared PDFs are snapshots: use
New Signing Revision after editing a source document.

Existing specialized PO, payment-voucher, contract, measurement and IPC flows are
intentionally excluded to preserve their attachment, posting and revision rules.
Other models already implementing action_send_to_sign are also excluded.
Wizard-only reports and SQL reporting models are not business document targets.

## Access and installation

Administrators configure integrations and generated views/server actions.
Sign users need normal source-document write access and report permission to
prepare/send. Reports, attachments, templates and requests retain their native
Odoo access controls. The source record is locked while preparing/sending, but
its business fields are not written. User history shows their own preparations
in allowed companies; administrators can review allowed-company history.

Generated views/actions have addon external IDs for uninstall cleanup.
Do not uninstall while signing history is in use without reviewing the retained
native templates, requests and source-linked PDF attachments.

## Validation

26 offline checks pass for source permissions, company/state/report restrictions,
single-record behavior, generated XML, duplicate-preparation guards and manifest
consistency. The existing 62 signing/placement checks also pass, including the
actual IPC PDF regression. These are not a native Odoo installation or browser
end-to-end test.

Seven database/native-view tests are included under tests/. Run on Odoo 18 using
--test-enable --test-tags /absar_send_to_sign_universal. They have not been run in
this workspace. They do not send invitations.

Staging acceptance before production:

- Activate an integration for Sales Order using its quotation/order PDF report;
  confirm one button, deactivate/reactivate, and confirm no duplicates.
- Set state=sale,done and verify draft quotations are rejected.
- Prepare one order with matching printed headings or saved positions. Verify
  signature/date placement and order in the native Send wizard.
- Test an unresolved heading and confirm it opens review without sending.
- Send one staging request, click the source button again, and verify no second
  request exists. Check native request progress in signing history.
- Check a second company/project uses its own workflow and source record rules.
- Change a workflow after preparing: the existing template must retain its
  original recipients; a new revision must use the updated workflow.
- Verify PO/PV/construction buttons still behave as before.
