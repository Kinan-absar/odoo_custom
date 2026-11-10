# ABSAR Payroll Employee Accrual Split

Version 18.0.1.1.5

## What it does
- Keeps **Batch Account Move Lines** enabled, so payroll stays in one accounting move.
- Splits only the configured accrued-salary liability account by employee partner.
- Uses the employee's existing linked partner automatically.
- Uses the payroll batch name as the journal-item label when available.

## Configuration
Go to **Payroll > Configuration > Employee Accrued Salary** and select the liability account used for accrued salaries.

The configuration is stored on the company but is no longer shown on the Company form.
The screen is standalone and does not inherit the main Payroll Settings view, avoiding XPath compatibility issues with Enterprise/localization views.
