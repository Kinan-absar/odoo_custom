# ABSAR Payroll Employee Accrual Split

Odoo 18 module for keeping a single batched payroll journal entry while splitting the configured accrued salary liability account into one line per employee partner.

## Configuration

Payroll > Configuration > Employee Accrued Salary

Choose the accrued salary liability account and keep **Batch Account Move Lines** enabled.

## v18.0.1.1.10

- Places the configuration menu directly under the confirmed Payroll > Configuration menu XML ID:
  `hr_work_entry_contract_enterprise.menu_hr_payroll_configuration`.
- Removes the previous dynamic menu-creation workaround.
- Keeps the existing payroll split behavior unchanged.
