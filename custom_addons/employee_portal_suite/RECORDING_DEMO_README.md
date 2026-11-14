# Employee Portal Suite 18.0.1.20.138 — Complete Module

Full Employee Portal Suite based on the supplied `employee_portal_suite(20261114-085957).zip` (18.0.1.20.135), with Recording Demo Setup integrated into the existing module. No separate recording add-on is needed.

## Install / upgrade and create examples

1. Replace the existing `employee_portal_suite` folder on your development/demo branch with the folder from this ZIP, then upgrade **Employee Portal Suite** from Apps.
2. As a Settings administrator, open **Employee Portal → Recording Demo Setup → New**.
3. Select the company and tick **This is a development/demo database**.
4. Leave **Include draft RFQ and draft vendor bill** enabled if the company has a purchase journal and expense account. Otherwise untick it; all 44 request examples and sample PDF attachments will still load.
5. Click **Create Recording Examples**. Then use the Employee Requests and Material Requests buttons to open the normal dashboards filtered to your recording batch.
6. Enable the optional **Demo Scenario** column to identify the cases. Existing approver accounts can be selected before creating the examples. All eight slots default to your current account. No login accounts are created or changed.

Samples are created only by the button, not automatically on upgrade. Reopening the same completed batch does not create duplicates. These sample records appear in request lists and reports, so use your demo database.

If the earlier separate `employee_portal_recording_demo` add-on was already installed, do not deploy this merged version alongside it: the two implementations use the same setup model. Continue using that add-on, or first return to the demo database backup taken before its installation and deploy this complete module there.

## Included

- **16 employee requests**, **28 material requests**, two projects and work locations.
- Four named requesting employees and eight sample role employees, without linked login accounts. The workflow steps use the existing approver accounts selected in the setup. By default all stages use the current administrator; choose different existing users for distinct approval-history names. No user groups or shared role definitions are changed.
- Project-specific employee workflows: Direct Manager → HR → Finance → CEO.
- Project-specific material workflows: Purchase Representative → Store Manager → Project Manager → Projects Director → CEO.
- Draft, every pending approval stage, fully approved, returned for correction, rejected, overdue, and an approved administrator-override example.
- Material clarification waiting for a reply, and a separate sample where a reply is already recorded.
- Real attached sample PDFs for quotations (0/3, 1/3, 2/3 and 3/3), general site requirements and employee supporting documents.
- Quotation exception and single-source approval examples.
- No-PO examples, plus an approved request ready to create a PO.
- Invoice PDF uploaded but not yet submitted; submitted to accounting; received; more documents requested; processed; rejected; and an additional delivery note uploaded after a prior submission.
- Optional **actual draft RFQ** linked to an MR and **actual draft vendor bill** linked to a No-PO MR, with sample lines and amounts. Neither is confirmed or posted.

The approval history is synthetic, clearly labeled recording data. It does not claim that approvals occurred in real operations. PDF fixtures are visibly marked DEMO SAMPLE and contain no actual supplier tax/bank data.

The “Processed” invoice case demonstrates the document-tracking status only. It does not mean an accounting entry was posted. The RFQ case is a draft, not a confirmed purchase order, goods receipt or supplier payment.

## Suggested recording order

1. Normal request dashboards: stage cards, counts and project filters.
2. Employee requests: manager, HR, finance, CEO, returned and rejected examples.
3. Material approvals: pending stages, history, overdue, clarification and override.
4. Steel supply: quotations 2/3; open both sample quotations.
5. Paint supply: quotations 3/3 and PO-required state.
6. Small tools: No PO Required and invoice pending.
7. Site tools: invoice uploaded but not submitted.
8. Invoice-document statuses: submitted, received, need more, processed and rejected.
9. Delivery paperwork: new attachment after previous submission.
10. Cable procurement: linked draft RFQ; small purchase: linked draft vendor bill.

## Technical checks and limits

Python compilation, XML parsing, inherited-view anchors, referenced suite fields, scenario coverage and PDF parsing are checked locally. Odoo runtime integration tests are included under `tests/` for a development database. An Odoo server is not installed in the authoring environment, so installation and full ORM execution have not been run here.

The integrated generator sets synthetic statuses at record creation, rather than calling submission/final-approval actions. It does not send invitation emails, confirm orders, post bills or update existing users/requests. Existing workflows remain unchanged; the new workflows apply only to the two new sample projects.

There is no cleanup/delete button. Reuse this batch while filming. Use a disposable development database or restore its backup when the samples are no longer needed. Uninstalling Employee Portal Suite is not a cleanup procedure for these samples.


## Backend-only user-type correction in 18.0.1.20.138

The setup does not call res.users.create or res.users.write, and it does not link sample employees to login accounts. This removes login provisioning and inherited-user-type validation from the recording generator. Existing users are used only as selected workflow approvers.

Upgrade this complete module, reopen your Not Created setup, verify the eight existing approver fields and click Create Recording Examples. All 44 backend request cases and their attachments remain included. These new requester employees cannot sign into the portal; use your existing real/demo portal accounts for separate portal recordings.
