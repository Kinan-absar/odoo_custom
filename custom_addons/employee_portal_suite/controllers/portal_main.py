from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError


class EmployeePortalMain(CustomerPortal):

    # ---------------------------------------------------------
    # EMPLOYEE PORTAL DASHBOARD (MAIN /my/employee)
    # ---------------------------------------------------------
    @http.route('/my/employee', type='http', auth='user', website=True)
    def employee_portal_dashboard(self, **kw):
        user = request.env.user
        employee = user.employee_id

        # ------------------------------------------------------
        # 1. My Employee Requests
        # ------------------------------------------------------
        my_request_count = request.env['employee.request'].sudo().search_count([
            ('employee_id', '=', employee.id)
        ])

        # ------------------------------------------------------
        # 2. My Material Requests
        # ------------------------------------------------------
        my_material_count = request.env['material.request'].sudo().search_count([
            ('employee_id.user_id', '=', user.id)
        ])

        # ------------------------------------------------------
        # 3. Employee Pending Approvals
        # ------------------------------------------------------
        employee_pending_count = 0

        pending_recs = request.env['employee.request'].sudo().search([
            ('state', 'in', ['manager', 'hr', 'finance', 'ceo'])
        ])

        for rec in pending_recs:
            if rec.state == 'manager' and user.has_group('employee_portal_suite.group_employee_portal_manager'):
                if rec.manager_id == employee:
                    employee_pending_count += 1
            elif rec.state == 'hr' and user.has_group('employee_portal_suite.group_employee_portal_hr'):
                employee_pending_count += 1
            elif rec.state == 'finance' and user.has_group('employee_portal_suite.group_employee_portal_finance'):
                employee_pending_count += 1
            elif rec.state == 'ceo' and user.has_group('employee_portal_suite.group_employee_portal_ceo'):
                employee_pending_count += 1

        # ------------------------------------------------------
        # 4. Material Pending Approvals
        # ------------------------------------------------------
        material_pending_count = 0
        Material = request.env['material.request'].sudo()

        pending_recs = Material.search([
            ('state', 'in', ['purchase', 'store', 'project_manager', 'director', 'ceo'])
        ])

        for rec in pending_recs:
            if rec.state == 'purchase' and user.has_group('employee_portal_suite.group_mr_purchase_rep'):
                material_pending_count += 1
            elif rec.state == 'store' and rec.store_manager_user_id == user:
                material_pending_count += 1
            elif rec.state == 'project_manager' and rec.project_manager_user_id == user:
                material_pending_count += 1
            elif rec.state == 'director' and user.has_group('employee_portal_suite.group_mr_projects_director'):
                material_pending_count += 1
            elif rec.state == 'ceo' and user.has_group('employee_portal_suite.group_employee_portal_ceo'):
                material_pending_count += 1
        
        # -------------------------------
        # 5. Documents to Sign
        # -------------------------------
        pending_sign_count = 0
        if "sign.request.item" in request.env:
            pending_sign_count = request.env["sign.request.item"].sudo().search_count([
                ('partner_id', '=', user.partner_id.id),
                ('state', '=', 'sent')
            ])
        
        # -------------------------------
        # 6. Construction Counts
        # -------------------------------
        contract_count = 0
        ipc_count = 0
        variation_count = 0
        measurement_count = 0
        
        if request.env['construction.contract'].check_access_rights('read', raise_exception=False):
            contract_count = request.env['construction.contract'].search_count([])
            ipc_count = request.env['construction.ipc'].search_count([])
            variation_count = request.env['construction.variation'].search_count([])
            measurement_count = request.env['construction.measurement'].search_count([])
        
        # ------------------------------------------------------
        # 7. Recent Activities
        # ------------------------------------------------------
        from itertools import chain

        EmployeeRequest = request.env['employee.request'].sudo()
        MaterialRequest = request.env['material.request'].sudo()

        recent_employee = EmployeeRequest.search(
            [('employee_id', '=', employee.id)],
            order='create_date desc',
            limit=5
        )

        recent_material = MaterialRequest.search(
            [('employee_id.user_id', '=', user.id)],
            order='create_date desc',
            limit=5
        )

        recent_activities = list(chain(recent_employee, recent_material))
        recent_activities = sorted(
            recent_activities,
            key=lambda r: r.create_date or r.write_date,
            reverse=True
        )[:6]

        # ------------------------------------------------------
        # Render
        # ------------------------------------------------------
        return request.render("employee_portal_suite.employee_portal_dashboard", {
            "my_request_count": my_request_count,
            "my_material_count": my_material_count,
            "employee_pending_count": employee_pending_count,
            "material_pending_count": material_pending_count,
            "pending_sign_count": pending_sign_count,
            "recent_activities": recent_activities,
            "contract_count": contract_count,
            "ipc_count": ipc_count,
            "variation_count": variation_count,
            "measurement_count": measurement_count,
        })

    # ---------------------------------------------------------
    # PETTY CASH
    # ---------------------------------------------------------
    @http.route("/my/employee/petty-cash", type="http", auth="user", website=True)
    def portal_petty_cash_list(self, **kw):
        user = request.env.user

        if not user.has_group("petty_cash_management.group_portal_petty_cash_user"):
            return request.redirect("/my")

        records = request.env["petty.cash"].search([
            ("user_id", "=", user.id)
        ])

        return request.render("employee_portal_suite.portal_petty_cash_list", {
            "records": records,
        })

    @http.route("/my/employee/petty-cash/new", type="http", auth="user", website=True)
    def portal_petty_cash_new(self, **kw):
        if not request.env.user.has_group("petty_cash_management.group_portal_petty_cash_user"):
            return request.redirect("/my")

        return request.render("employee_portal_suite.portal_petty_cash_new")

    # ---------------------------------------------------------
    # CONSTRUCTION - CONTRACTS
    # ---------------------------------------------------------
    @http.route(['/my/employee/contracts', '/my/employee/contracts/page/<int:page>'], 
                type='http', auth='user', website=True)
    def portal_construction_contracts(self, page=1, sortby=None, filterby=None, **kw):
        user = request.env.user

        if not request.env['construction.contract'].check_access_rights('read', raise_exception=False):
            return request.redirect("/my/employee")

        values = self._prepare_portal_layout_values()
        ConstructionContract = request.env['construction.contract']

        domain = []
        searchbar_sortings = {
            'date': {'label': 'Newest', 'order': 'id desc'},
            'name': {'label': 'Name', 'order': 'name'},
            'partner': {'label': 'Partner', 'order': 'partner_id'},
        }
        searchbar_filters = {
            'all': {'label': 'All', 'domain': []},
            'draft': {'label': 'Draft', 'domain': [('state', '=', 'draft')]},
            'under_review': {'label': 'Under Review', 'domain': [('state', '=', 'under_review')]},
            'approved': {'label': 'Approved', 'domain': [('state', '=', 'approved')]},
            'active': {'label': 'Active', 'domain': [('state', '=', 'active')]},
            'completed': {'label': 'Completed', 'domain': [('state', '=', 'completed')]},
        }

        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        contract_count = ConstructionContract.search_count(domain)

        pager = portal_pager(
            url="/my/employee/contracts",
            url_args={'sortby': sortby, 'filterby': filterby},
            total=contract_count,
            page=page,
            step=self._items_per_page
        )

        contracts = ConstructionContract.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'contracts': contracts,
            'page_name': 'construction_contract',
            'default_url': '/my/employee/contracts',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': searchbar_filters,
            'sortby': sortby,
            'filterby': filterby,
        })
        return request.render("construction_contract_management.portal_employee_contracts", values)

    @http.route(['/my/employee/contract/<int:contract_id>'], type='http', auth='user', website=True)
    def portal_construction_contract_detail(self, contract_id, access_token=None, **kw):
        try:
            contract_sudo = self._document_check_access('construction.contract', contract_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        values = {
            'contract': contract_sudo,
            'page_name': 'construction_contract',
        }
        return request.render("construction_contract_management.portal_employee_contract_detail", values)

    # ---------------------------------------------------------
    # CONSTRUCTION - IPCs
    # ---------------------------------------------------------
    @http.route(['/my/employee/ipcs', '/my/employee/ipcs/page/<int:page>'], 
                type='http', auth='user', website=True)
    def portal_construction_ipcs(self, page=1, sortby=None, filterby=None, **kw):
        user = request.env.user

        if not request.env['construction.ipc'].check_access_rights('read', raise_exception=False):
            return request.redirect("/my/employee")

        values = self._prepare_portal_layout_values()
        ConstructionIPC = request.env['construction.ipc']

        domain = []
        searchbar_sortings = {
            'date': {'label': 'Newest', 'order': 'id desc'},
            'name': {'label': 'Reference', 'order': 'name'},
            'contract': {'label': 'Contract', 'order': 'contract_id'},
        }
        searchbar_filters = {
            'all': {'label': 'All', 'domain': []},
            'draft': {'label': 'Draft', 'domain': [('state', '=', 'draft')]},
            'under_review': {'label': 'Under Review', 'domain': [('state', '=', 'under_review')]},
            'approved': {'label': 'Approved', 'domain': [('state', '=', 'approved')]},
            'done': {'label': 'Done', 'domain': [('state', '=', 'done')]},
        }

        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        ipc_count = ConstructionIPC.search_count(domain)

        pager = portal_pager(
            url="/my/employee/ipcs",
            url_args={'sortby': sortby, 'filterby': filterby},
            total=ipc_count,
            page=page,
            step=self._items_per_page
        )

        ipcs = ConstructionIPC.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'ipcs': ipcs,
            'page_name': 'construction_ipc',
            'default_url': '/my/employee/ipcs',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': searchbar_filters,
            'sortby': sortby,
            'filterby': filterby,
        })
        return request.render("construction_contract_management.portal_employee_ipcs", values)

    @http.route(['/my/employee/ipc/<int:ipc_id>'], type='http', auth='user', website=True)
    def portal_construction_ipc_detail(self, ipc_id, access_token=None, report_type=None, download=False, **kw):
        try:
            ipc_sudo = self._document_check_access('construction.ipc', ipc_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        if report_type in ('html', 'pdf', 'text'):
            return self._show_report(model=ipc_sudo, report_type=report_type, 
                                    report_ref='construction_contract_management.action_report_construction_ipc', 
                                    download=download)

        values = {
            'ipc': ipc_sudo,
            'page_name': 'construction_ipc',
        }
        return request.render("construction_contract_management.portal_employee_ipc_detail", values)

    # ---------------------------------------------------------
    # CONSTRUCTION - VARIATIONS
    # ---------------------------------------------------------
    @http.route(['/my/employee/variations', '/my/employee/variations/page/<int:page>'], 
                type='http', auth='user', website=True)
    def portal_construction_variations(self, page=1, sortby=None, filterby=None, **kw):
        user = request.env.user

        if not request.env['construction.variation'].check_access_rights('read', raise_exception=False):
            return request.redirect("/my/employee")

        values = self._prepare_portal_layout_values()
        ConstructionVariation = request.env['construction.variation']

        domain = []
        searchbar_sortings = {
            'date': {'label': 'Newest', 'order': 'id desc'},
            'name': {'label': 'Reference', 'order': 'name'},
        }
        searchbar_filters = {
            'all': {'label': 'All', 'domain': []},
            'draft': {'label': 'Draft', 'domain': [('state', '=', 'draft')]},
            'under_review': {'label': 'Under Review', 'domain': [('state', '=', 'under_review')]},
            'approved': {'label': 'Approved', 'domain': [('state', '=', 'approved')]},
        }

        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        variation_count = ConstructionVariation.search_count(domain)
        
        pager = portal_pager(
            url="/my/employee/variations",
            url_args={'sortby': sortby, 'filterby': filterby},
            total=variation_count,
            page=page,
            step=self._items_per_page
        )

        variations = ConstructionVariation.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'variations': variations,
            'page_name': 'construction_variation',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': searchbar_filters,
            'sortby': sortby,
            'filterby': filterby,
        })
        return request.render("construction_contract_management.portal_employee_variations", values)

    @http.route(['/my/employee/variation/<int:variation_id>'], type='http', auth='user', website=True)
    def portal_construction_variation_detail(self, variation_id, access_token=None, **kw):
        try:
            variation_sudo = self._document_check_access('construction.variation', variation_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        values = {
            'variation': variation_sudo,
            'page_name': 'construction_variation',
        }
        return request.render("construction_contract_management.portal_employee_variation_detail", values)

    # ---------------------------------------------------------
    # CONSTRUCTION - MEASUREMENTS
    # ---------------------------------------------------------
    @http.route(['/my/employee/measurements', '/my/employee/measurements/page/<int:page>'], 
                type='http', auth='user', website=True)
    def portal_construction_measurements(self, page=1, sortby=None, filterby=None, **kw):
        user = request.env.user

        if not request.env['construction.measurement'].check_access_rights('read', raise_exception=False):
            return request.redirect("/my/employee")

        values = self._prepare_portal_layout_values()
        ConstructionMeasurement = request.env['construction.measurement']

        domain = []
        searchbar_sortings = {
            'date': {'label': 'Newest', 'order': 'id desc'},
            'name': {'label': 'Reference', 'order': 'name'},
        }
        searchbar_filters = {
            'all': {'label': 'All', 'domain': []},
            'draft': {'label': 'Draft', 'domain': [('state', '=', 'draft')]},
            'approved': {'label': 'Approved', 'domain': [('state', '=', 'approved')]},
        }

        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        measurement_count = ConstructionMeasurement.search_count(domain)
        
        pager = portal_pager(
            url="/my/employee/measurements",
            url_args={'sortby': sortby, 'filterby': filterby},
            total=measurement_count,
            page=page,
            step=self._items_per_page
        )

        measurements = ConstructionMeasurement.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'measurements': measurements,
            'page_name': 'construction_measurement',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': searchbar_filters,
            'sortby': sortby,
            'filterby': filterby,
        })
        return request.render("construction_contract_management.portal_employee_measurements", values)

    @http.route(['/my/employee/measurement/<int:measurement_id>'], type='http', auth='user', website=True)
    def portal_construction_measurement_detail(self, measurement_id, access_token=None, **kw):
        try:
            measurement_sudo = self._document_check_access('construction.measurement', measurement_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        values = {
            'measurement': measurement_sudo,
            'page_name': 'construction_measurement',
        }
        return request.render("construction_contract_management.portal_employee_measurement_detail", values)

# ---------------------------------------------------------
    # CONSTRUCTION - NEW MEASUREMENT FORM
    # ---------------------------------------------------------
    @http.route(['/my/employee/measurement/new'], type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_construction_measurement_new(self, **post):
        user = request.env.user

        if not request.env['construction.measurement'].check_access_rights('create', raise_exception=False):
            return request.redirect("/my/employee")

        if request.httprequest.method == 'POST':
            # Create the measurement
            vals = {
                'contract_id': int(post.get('contract_id')),
                'date': post.get('date'),
                'period_from': post.get('period_from'),
                'period_to': post.get('period_to'),
                'description': post.get('description', ''),
            }
            
            measurement = request.env['construction.measurement'].create(vals)
            
            return request.redirect(f'/my/employee/measurement/{measurement.id}')
        
        # GET request - show form
        contracts = request.env['construction.contract'].search([('state', 'in', ['active', 'approved'])])
        
        values = {
            'contracts': contracts,
            'page_name': 'construction_measurement_new',
        }
        return request.render("construction_contract_management.portal_employee_measurement_new", values)

    # ---------------------------------------------------------
    # CONSTRUCTION - NEW VARIATION FORM
    # ---------------------------------------------------------
    @http.route(['/my/employee/variation/new'], type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_construction_variation_new(self, **post):
        user = request.env.user

        if not request.env['construction.variation'].check_access_rights('create', raise_exception=False):
            return request.redirect("/my/employee")

        if request.httprequest.method == 'POST':
            # Create the variation
            vals = {
                'contract_id': int(post.get('contract_id')),
                'date': post.get('date'),
                'description': post.get('description', ''),
            }
            
            # Add reason if provided
            if post.get('reason'):
                vals['description'] = vals['description'] + '\n\nReason: ' + post.get('reason')
            
            variation = request.env['construction.variation'].create(vals)
            
            return request.redirect(f'/my/employee/variation/{variation.id}')
        
        # GET request - show form
        contracts = request.env['construction.contract'].search([('state', 'in', ['active', 'approved'])])
        
        values = {
            'contracts': contracts,
            'page_name': 'construction_variation_new',
        }
        return request.render("construction_contract_management.portal_employee_variation_new", values)
