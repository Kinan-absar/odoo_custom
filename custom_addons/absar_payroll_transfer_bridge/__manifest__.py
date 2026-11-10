{
    "name": "ABSAR Payroll Transfer Bridge",
    "summary": "Pay a complete payroll batch through one Payment Voucher while clearing accrued salaries by employee partner",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "author": "ABSAR",
    "license": "LGPL-3",
    "depends": [
        "internal_transfer_voucher",
        "absar_payroll_employee_accrual",
    ],
    "data": [
        "views/payment_voucher_views.xml",
    ],
    "installable": True,
    "application": False,
}
