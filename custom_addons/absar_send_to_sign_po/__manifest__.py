{
    'name': 'Send to Sign for Purchase Orders',
    'version': '1.0.0',
    'summary': 'Digital signing workflow for purchase orders using Odoo Sign.',
    'description': """
        Digital Signing Workflow for Purchase Orders
        --------------------------------------------
        
        This module enhances the Purchase Order workflow by integrating Odoo Sign
        and adding automated revision/version control.
        
        Key Features:
        • Adds a “Send to Sign” button for confirmed Purchase Orders.
        • Generates a printable PO PDF and sends it to Odoo Sign for digital signatures.
        • Automatically tracks signature progress and updates PO signature state.
        • Displays signature status inside the form view and list view.
        • Implements full revision control (R-1, R-2, …) for signed POs.
        • Automatically resets signature state and increments revision when PO data changes.
        • Shows revision number directly in the PO PDF.
        • Prevents repeated signing unless changes are made after the last completed signature.
        
        This provides a clean, controlled, and auditable digital approval process for purchasing.
            """,
    'author': 'Kinan',
    'website': 'https://absar-alomran.com',
    'category': 'Purchases',
    'depends': ['purchase', 'sign', 'mail'],
    'data': [
        'data/cron.xml',
        'views/purchase_order_view.xml',
        'views/res_company_view.xml',
        'views/report_purchaseorder_inherit.xml',
        
        ],

    'installable': True,
    'application': False,
}
