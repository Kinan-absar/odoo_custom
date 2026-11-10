ABSAR Payroll Employee Accrual Split - v18.0.1.1.13

Purpose
-------
Keep Batch Account Move Lines enabled so payroll stays in one journal entry, while the configured accrued-salary liability account is split into one journal line per employee partner.

Configuration
-------------
Payroll -> Configuration -> Settings -> Payroll Accounting -> Employee Accrued Salary

Implementation note
-------------------
The setting is added using the same stable Odoo 18 Settings pattern used by the working Portal Backend Workspace module: inherit the application's settings view, target the Payroll app container itself, and add a dedicated block inside it. It does not target Batch Account Move Lines or any sibling inherited view.
