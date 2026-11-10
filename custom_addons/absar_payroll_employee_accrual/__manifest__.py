{
    "name": "ABSAR Payroll Employee Accrual Split",
    "summary": "Keep one batched payroll journal entry while splitting accrued salaries by employee partner",
    "version": "18.0.1.0.0",
    "category": "Human Resources/Payroll",
    "author": "ABSAR",
    "license": "LGPL-3",
    "depends": ["hr_payroll_account"],
    "data": [
        "views/res_company_views.xml",
        "views/hr_employee_views.xml",
    ],
    "installable": True,
    "application": False,
}
