# ABSAR Payroll Employee Accrual Split

Version 18.0.1.1.6

- Keeps one batched payroll journal entry.
- Splits the configured accrued salary liability account by employee partner.
- Keeps salary expense lines grouped.
- Uses existing employee-linked partners automatically.
- Uses the payroll batch name as the accrued-line label when available.
- Configuration is available from Payroll > Configuration > Employee Accrued Salary.
- The Payroll Configuration parent menu is resolved dynamically, so no fragile Payroll menu XML ID is hard-coded.
