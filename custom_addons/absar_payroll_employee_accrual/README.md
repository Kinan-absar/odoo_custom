# ABSAR Payroll Employee Accrual Split - Odoo 18

## Purpose
Keep **Batch Account Move Lines** enabled so Odoo creates one payroll journal entry per payroll period, while keeping the configured accrued salary liability account separated into one journal item per employee partner.

## Version 18.0.1.1.0 changes
- Removed the setting from **Settings > Companies**.
- Moved **Accrued Salary Account** to **Payroll > Configuration > Settings > Accounting**.
- Removed the extra **Payroll Accounting Partner** field/tab from employees.
- The module now automatically uses the employee's existing linked Odoo partner/contact.
- Accrued salary journal labels no longer repeat the employee name. The label uses the payroll batch name when available, otherwise the journal reference/payroll period.

## Configuration
1. Upgrade/install this module.
2. Open **Payroll > Configuration > Settings**.
3. Keep **Payroll Entries** enabled.
4. Keep **Batch Account Move Lines** enabled.
5. Under **Accounting**, set **Employee Accrued Salary Split > Accrued Salary Account** to your liability account (for example `203003 Accrued - Salaries`).
6. Save.

## Expected result
One monthly/batch journal entry, with expense accounts still grouped, while the accrued salary account appears once per employee with the employee in the **Partner** column.

Example:

| Account | Partner | Label | Debit | Credit |
|---|---|---|---:|---:|
| Basic Salary | | September 2026 | 70,000 | |
| Housing | | September 2026 | 15,000 | |
| Accrued Salaries | Employee A | September 2026 | | 30,000 |
| Accrued Salaries | Employee B | September 2026 | | 25,000 |
| Accrued Salaries | Employee C | September 2026 | | 30,000 |

## Notes
- Existing posted payroll entries are not rewritten. Test with a new draft payroll batch.
- The module checks that the employee-by-employee total exactly matches Odoo's original accrued salary total before replacing the batched liability line.
