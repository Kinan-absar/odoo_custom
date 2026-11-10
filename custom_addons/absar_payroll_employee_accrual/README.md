# ABSAR Payroll Employee Accrual Split — v18.0.1.1.11

## Configuration
Go to **Payroll → Configuration → Settings → Accounting**.

A new **Employee Accrued Salary** setting appears directly below **Batch Account Move Lines**. Select the accrued salary liability account there.

Keep **Batch Account Move Lines** enabled.

## Behavior
- One batched payroll journal entry remains.
- The configured accrued salary account is split into one journal line per employee partner.
- Other salary expense lines remain grouped normally.
- The accrued salary line label uses the payroll batch name when available, otherwise the journal reference/payroll period.
- No payroll-specific partner field is added to employees; the module uses the employee's existing linked partner/contact.
