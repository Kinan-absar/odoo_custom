{
    "name": "Send to Sign for Purchase Orders",
    "version": "18.0.1.1.1",
    "summary": "Configurable digital signing workflow for Purchase Orders using Odoo Sign",
    "author": "Kinan",
    "website": "https://absar-alomran.com",
    "category": "Purchases",
    "license": "LGPL-3",
    "depends": ["purchase", "absar_sign_workflow_core"],
    "data": [
        "security/ir.model.access.csv",
        "data/cron.xml",
        "views/purchase_order_view.xml",
        "views/report_purchaseorder_inherit.xml",
        "views/legacy_cleanup.xml"
    ],
    "installable": True,
    "application": False,
}
