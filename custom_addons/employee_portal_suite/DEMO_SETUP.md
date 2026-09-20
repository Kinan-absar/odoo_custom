# Employee Portal Suite - On-Demand Demo Setup (Odoo 18)

This build adds an administrator-only **Employee Portal > Demo Setup** wizard intended for disposable Odoo.sh Development databases.

## What it prepares

- Demo Manager / Approver (internal user)
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
