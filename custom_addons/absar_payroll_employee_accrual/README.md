# ABSAR Payroll Employee Accrual Split (Odoo 18)

## Goal
Keep **one payroll journal entry for the month** while keeping **Accrued Salaries split per employee partner**.

Example:

- Basic Salary Expense: grouped
- Housing Expense: grouped
- Transportation Expense: grouped
- Accrued Salaries / Employee A: separate credit line
- Accrued Salaries / Employee B: separate credit line
- Accrued Salaries / Employee C: separate credit line

This is designed for Odoo 18 with `hr_payroll_account` and **Batch Account Move Lines enabled**.

## Install
1. Put `absar_payroll_employee_accrual` in your custom addons repository.
2. Update Apps List.
3. Install **ABSAR Payroll Employee Accrual Split**.
4. Go to **Settings > Companies > your company > Payroll Accounting**.
5. Set **Payroll Accrued Salary Account** to `203003 Accrued - Salaries` (or your actual liability account).
6. Go to each Employee > **Payroll Accounting** and set **Payroll Accounting Partner** if Odoo does not already have a usable linked contact for that employee.
7. In **Payroll > Configuration > Settings**, keep **Batch Account Move Lines = ON**.

## What the module changes
After standard Odoo creates the draft batched payroll move, this module:

1. Reads all payslips attached to that move.
2. Reconstructs the amount belonging to the configured accrued salary account per employee from salary-rule debit/credit accounts.
3. Verifies the reconstructed total exactly matches Odoo's original total for that account.
4. Removes only the original aggregated lines for that accrued account.
5. Recreates one line per employee with `partner_id` populated.
6. Leaves expense lines and all other accounts untouched.

## Safety
The module refuses to modify the move when:
- the payroll journal entry is already posted;
- an employee has no usable partner;
- reconstructed employee totals do not match Odoo's original accrued-salary total;
- the resulting move would be unbalanced.

Test first on Staging with 2-3 employees before installing on Main.
