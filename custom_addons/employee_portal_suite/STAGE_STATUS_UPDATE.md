# Approval stage status — 18.0.1.20.90

Employee Requests and Material Requests display their actual pending workflow step in backend lists and form headers. Pending steps receive 12 distinct colors by snapshot sequence rank; colors repeat after 12 stages. Draft is gray, returned/clarification is orange, approved is green, and rejected is red. Stage text remains visible so color is not the only indicator. Legacy stages also receive separate colors in list badges.

This is a display update. Approval decisions, roles, project mappings, return-for-correction logic, and existing request snapshots are preserved.

## Upgrade and test

Replace the existing employee_portal_suite folder with this folder, commit/push to staging, then upgrade Employee Portal Suite through Apps. Reload the browser to load the new assets.

1. Submit a new Material Request for Office. Confirm that the dynamic workflow timeline contains five steps and the first-stage badge appears.
2. Advance approvals using the configured approvers. Confirm the label and color change at each stage.
3. Repeat with a new Employee Request. Check Manager, HR, Finance and CEO stages.
4. Return a request for correction, resubmit it, then approve or reject it. Check the status text and reserved colors.
5. Check old requests and clarification records still retain their original route and labels.

## Staging inspection on 2026-10-11

Both currently active workflows have no project restriction; the Employee Request workflow also has no request-type restriction. Therefore they act as company-wide defaults.

Office MR-00737 was submitted at 11:18 and entered the legacy Purchase Representative state. The currently active Material Request workflow was validated at 11:49. Validation time is not proof of exact activation time; the old request nevertheless clearly contains the legacy route. Existing submissions are not automatically migrated when configuration changes.

The live Material Request Test / Preview resolved all five approver stages for Office and the selected employee. This was a preview, not a new request submission or approval. If a newly submitted request still uses the legacy route, inspect the selected company and submission-time active workflow, rather than changing the status display.

The Employee Request workflow has a runtime-manager warning. Each requester needs a resolvable manager. Project-specific approval roles must also resolve for the selected project.

## Validation limits

Offline checks passed for Python/XML syntax, view inheritance, stage label advancement, distinct stage colors, semantic status colors and clarification preservation. JavaScript syntax passed. Version 90 has not yet been upgraded or rendered in a live Odoo database.
