# 18.0.0.9.12

- Fix upgrade failure after removing the Employee Admin Payslip Report setting.
- Restore `pbw_hr_payslip_report_id` as a hidden compatibility field only, so Odoo can validate and remove legacy installed views during upgrade.
- The field is not exposed in Company Settings and is not used for payslip printing.
- Payslip printing continues to use the native Odoo Payroll report.
