{
    "name": "PO Payment Link",
    "version": "1.0.0",
    "summary": "Link vendor payments to Purchase Orders and show payment status",
    "category": "Purchases",
    "depends": [
        "purchase",
        "account",
    ],
    "data": [
        "views/account_payment_view.xml",
        "views/purchase_order_view.xml",
    ],
    "installable": True,
    "application": False,
}
