{
    'name': 'Employee Portal Suite',
    'version': '1.0.0',
    'summary': 'Employee & Material Requests, Portal Approvals, and Digital Signing',

    'description': """
        Employee Portal Suite is a comprehensive self-service portal and approval management system designed to simplify internal operations for companies of all sizes.

        This module provides employees, managers, and executives with a unified portal experience to:
        • Submit structured requests
        • Track approval progress
        • Manage material needs
        • Generate PDF reports
        • Sign documents electronically
        —all within a secure and customizable portal.

        Key Features:
        ----------------
        • Clean, modern employee portal experience  
        • Multi-level approval workflows for Employee Requests  
        • Material Requests workflow with approval hierarchy  
        • Manager & Approver centralized approval center  
        • Automatic request numbering (Employee & Material)  
        • Full approval timelines and history  
        • Detail pages with attachments and comments  
        • PDF generation for all request types  
        • Integrated electronic document signing using Odoo Sign  
        • Secure portal access and isolation (employees see only their own data)  

        Approval workflows:
        -------------------
        Employee Requests:
        Employee → Manager → HR → Finance → CEO

        Material Requests:
        Employee → Purchase → Store → Project Manager → Director → CEO

        Target Users:
        -------------
        • Construction companies  
        • Engineering & services firms  
        • Mid-size to large enterprises with formal approval processes  
        • Organizations using Odoo Portal for internal services

        Benefits:
        ---------
        • Reduces manual paperwork  
        • Improves approval transparency  
        • Centralizes employee services  
        • Enhances accountability and traceability
    """,
    'license': 'OPL-1',
    'price': 249.99,
    'currency': 'USD',
    'author': 'Kinan',
    'category': 'Human Resources',
    'application': True,
    'installable': True,

    # ------------------------------------------------------------------
    #  DEPENDENCIES
    # ------------------------------------------------------------------
    'depends': [
        'base',
        'web',
        'portal',
        'hr',
        'mail',
        'hr_attendance',
        'website',
        'purchase',
        'sign',
        'project',
        'account',
    ],

    # ------------------------------------------------------------------
    #  DATA FILES LOADED IN ORDER
    # ------------------------------------------------------------------
    'data': [
        # --- SECURITY ---
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',

        # --- DATA / SEQUENCES ---
        'data/request_sequence.xml',
        'views/hr_employee_user_domain.xml',

        # --------------------------------------------------
        # REPORTS
        # --------------------------------------------------
        'reports/report_action.xml',
        'reports/report_employee_request.xml',
        'reports/report_material_request.xml',

        # --- BACKEND VIEWS ---
        'views/employee_request_views.xml',
        'views/material_request_views.xml',
        'views/menus.xml',
        
        # --------------------------------------------------
        # EMPLOYEE PORTAL (FRONTEND)
        # --------------------------------------------------
        'views/employee_portal_layout.xml',
        'views/employee_dashboard_page.xml',

        # Employee Requests
        'views/employee_requests_page.xml',
        'views/employee_request_detail_page.xml',
        'views/employee_request_new_form.xml',

        # --------------------------------------------------
        # MATERIAL REQUEST PORTAL (FRONTEND)
        # --------------------------------------------------
        'views/employee_material_requests_page.xml',
        'views/employee_material_request_detail_page.xml',
        'views/employee_material_request_new_form.xml',

        # --------------------------------------------------
        # MANAGER PORTAL (APPROVALS)
        # --------------------------------------------------
        'views/portal_material_approval_detail.xml',
        'views/portal_employee_approvals_list.xml',
        'views/portal_material_approvals_list.xml',
        'views/portal_manager_request_detail.xml',
        'views/portal_sign_documents.xml',
        'views/purchase_order_views.xml',
        'views/sign_portal_clean.xml',
        'views/hr_work_location_views.xml',
        'views/project_project_views.xml',

    ],

    # ------------------------------------------------------------------
    #  ASSETS (JS)
    # ------------------------------------------------------------------
    'assets': {
        
    },
    'images': ['images/main_screenshot.png'],

}
