# Employee Portal Suite — 18.0.1.20.89

Built from the supplied `employee_portal_suite(20261011-095700).zip` (18.0.1.20.88).

The Employee Request and Material Request backend Status badges now show the current configured approval step name instead of the generic Workflow Approval label. For example, Purchase Representative becomes Store Manager, then Project Manager, Projects Director and CEO as the request advances. Each project's configured names are used; they are not hard-coded. The request form shows the same stage badge while a configurable workflow is pending, and its Workflow tab still shows the full route/history.

Returned requests show the stage that returned them for correction. Legacy stage labels and completed/rejected statuses are retained, as is the MR Needs Clarification display. The actual `state` field and approval actions/permissions are unchanged. Existing portal status badges already resolve the pending step and are unchanged. Version 88's supplied styling, workflow templates, delivery-date validation and all other files are retained.

Replace the whole `employee_portal_suite` folder, push to staging, and Upgrade Employee Portal Suite. Confirm version 18.0.1.20.89. Existing requests do not need to be resubmitted. On a test request with a configured workflow, check the Status column and form before and after advancing the approval; also check a legacy request and a request marked for clarification.

Offline checks passed for Python/XML syntax, actual status computation with changing/custom steps, returned and legacy states, clarification badges, dependency declarations and inherited-view XPath targets. Live Odoo installation and view rendering have not been tested here.

Run offline checks with `python employee_portal_suite/tools/validate_stage_status.py`.
