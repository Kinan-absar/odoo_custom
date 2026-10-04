# Employee Portal Suite - On-Demand Demo Setup (Odoo 18)

This build adds an administrator-only **Employee Portal > Demo Setup** wizard intended for disposable Odoo.sh Development databases.

## What it prepares

- Demo Manager / Super Administrator (internal user)
- Two portal employees
- Correct Employee Portal, attendance, manager, HR, finance, CEO and material-request groups
- Linked HR employee records and manager hierarchy
- Demo department, project and work location
- Sample employee requests in several workflow stages
- Sample material request and lines
- Sample attendance records
- Welcome announcement
- Project approvers for the material-request workflow

## Default demo logins

The password is selected in the wizard (default: `Demo123!`).

- `manager@eps-demo.local`
- `employee1@eps-demo.local`
- `employee2@eps-demo.local`

The wizard is idempotent for its specifically named demo records, so **Prepare / Reset Demo** can be run again to refresh them and reset the demo-user passwords.

## Safety

The wizard is only visible to Odoo Settings administrators (`base.group_system`) and requires explicit confirmation that the database is disposable. Do not run it in production.


## Manager Setup Tour (20.86)

The backend Manager Setup Tour now follows the current workflow architecture:

1. Contact and portal access
2. Matching Employee and Related User
3. Department, Direct Manager and Work Locations
4. Work Location → Project / geofence mapping
5. Roles & Permissions (built-in access groups)
6. Approval Roles (custom business roles such as Commercial Manager or Cost Control)
7. Project Role Assignments (who performs each approval role on each project)
8. Workflows (separate configurable ER and MR workflows, with unlimited ordered steps)
9. Employee Request and Material Request examples
10. Employee Portal testing

The old tour step that treated Project Store Manager / Project Manager fields as the primary workflow configuration has been removed. Those legacy/default approvers may still exist for fallback behavior, but the tour now teaches the configurable workflow engine.

The fictional Demo Manager is also granted Odoo HR Officer access so the tour can open Employee and Work Location screens. This is scoped only to the demo login `manager@eps-demo.local`; Employee Portal Super Administrator remains independent from native HR permissions for real users.
