# ABSAR Payroll Employee Accrual Split

Version 18.0.1.1.7

- Keeps Batch Account Move Lines enabled and one payroll journal entry.
- Splits only the configured accrued salary liability account by employee partner.
- Configuration is opened from Payroll > Configuration > Employee Accrued Salary.
- Uses a dedicated Payroll configuration wizard, not `res.config.settings`, so opening it stays inside the Payroll app instead of switching to the Settings app.
- The selected account is stored per company.


Version 18.0.1.1.8: places Employee Accrued Salary directly under Payroll > Configuration without falling back to the global Settings app.

## v18.0.1.1.9
- Payroll Configuration menu placement now anchors to the confirmed standard menu XML ID `hr_payroll.menu_hr_payroll_global_settings`.
- The custom menu is attached to the exact same parent as Payroll > Configuration > Settings.
