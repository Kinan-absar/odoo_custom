# ABSAR Payroll Transfer Bridge (Odoo 18)

Technical name: `absar_payroll_transfer_bridge`

## Purpose

This bridge connects:

- `internal_transfer_voucher`
- `absar_payroll_employee_accrual`

When both are installed, Payment Vouchers gain a new payment method: **Payroll Transfer**.

## Workflow

1. Payroll is processed normally.
2. `absar_payroll_employee_accrual` creates one payroll journal entry while keeping the configured accrued salary account split by employee partner.
3. Post the payroll journal entry.
4. Create one Payment Voucher and select **Payroll Transfer**.
5. Select the Payroll Batch and the source Bank/Cash journal.
6. The voucher reads the *posted accounting lines* of that payroll batch. It does not recalculate salary rules.
7. Odoo fills the total automatically and posts one payment JV:
   - Dr Accrued Salaries - Employee A
   - Dr Accrued Salaries - Employee B
   - ...
   - Cr Bank/Cash - one total line

No employee lines are entered manually.

## Why the source is the payroll journal entry

The posted payroll JV is the accounting source of truth. Reading its employee-partner accrued lines guarantees the payment voucher agrees with the amount actually accrued, including any payroll rule or localization changes.

## Reconciliation

If the configured accrued salary account has **Allow Reconciliation** enabled, the bridge automatically reconciles each employee's payroll accrual credit with the corresponding payroll transfer debit. This gives clean employee statements and outstanding balances.

If reconciliation is not enabled, the voucher still posts the correct partner lines, but they remain unreconciled.

## Safety

- One active Payroll Transfer voucher per Payroll Batch.
- Requires posted payroll journal entries.
- Voucher total is taken automatically from the accrued salary lines.
- Normal Payment Voucher methods are unchanged.
- Payroll Transfer does not create a single-partner cash-planning line because the payment represents many employee partners.


## 18.0.1.0.2
- Fix mandatory Amount error on new Payroll Transfer vouchers.
- The computed payroll amount is now force-saved by the form and recomputed server-side during create as a safety net.
