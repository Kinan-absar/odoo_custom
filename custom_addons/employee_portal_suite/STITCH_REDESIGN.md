# Absar Employee Workspace - Stitch Redesign

This build adapts the Google Stitch "Kinetic Enterprise" design export to the existing Employee Portal Suite without replacing its backend workflows.

## Applied
- Fixed desktop sidebar with role-based navigation and active states.
- Compact desktop top bar with notifications/profile.
- Stitch color, typography, spacing, borders, tables, inputs, buttons and badges.
- Rebuilt employee dashboard around "Needs your attention", workspace cards and recent activity.
- Responsive mobile styling while retaining the existing bottom navigation and FAB actions.
- Restyled request lists, approval lists, detail cards, signatures, attendance, salary reports and report views through the shared design layer.
- Updated Employee Request and Material Request form hierarchy while preserving English/Arabic forms and their existing JavaScript/backend behavior.
- Preserved all routes, QWeb variables, permissions, approval flows and controller logic.

## Main design file
`static/src/css/stitch_workspace.css`

## Main structural templates changed
- `views/employee_portal_layout.xml`
- `views/employee_dashboard_page.xml`
- `views/employee_request_new_form.xml`
- `views/employee_material_request_new_form.xml`
- `views/portal_employee_approvals_list.xml`
- `views/portal_material_approvals_list.xml`
- `views/portal_sign_documents.xml`
