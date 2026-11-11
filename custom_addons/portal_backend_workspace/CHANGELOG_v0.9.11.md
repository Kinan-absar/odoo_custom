# 18.0.0.9.11 — HR company settings cleanup

- Removed the legacy **Employee Admin Portal / Employee Admin Payslip Report** block from the company form.
- HR payslip printing now uses Odoo's native `hr_payroll.action_report_payslip` report directly.
- Added an upgrade migration that removes the previously installed inherited company view, so upgrading an existing database removes the old block without uninstalling the module.
- No HR workspace access groups, forms, payroll records, or other workspace features are changed.
