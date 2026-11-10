{
    "name": "ABSAR Payroll Employee Accrual Split",
    "summary": "Keep one batched payroll journal entry while splitting accrued salaries by employee partner",
    "version": "18.0.1.1.10",
    "category": "Human Resources/Payroll",
    "author": "ABSAR",
    "license": "LGPL-3",
    "depends": ["hr_payroll_account", "hr_work_entry_contract_enterprise"],
    "data": [
        "views/payroll_accrual_config_views.xml",
    ],
    "installable": True,
    "application": False,
}
