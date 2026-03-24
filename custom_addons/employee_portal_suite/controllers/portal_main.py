from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError, ValidationError


class EmployeePortalMain(CustomerPortal):

    def _portal_visible_contract_domain(self):
        user = request.env.user
        if user:
            return ['|', ('portal_visibility_restricted', '=', False), ('portal_employee_ids.user_id', '=', user.id)]
        return [('portal_visibility_restricted', '=', False)]

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
        contract = request.env['construction.contract'].search([
            ('id', '=', contract_id),
        ] + self._portal_visible_contract_domain(), limit=1)
        if not contract:
            return request.redirect('/my/employee')

        values = {
            'contract': contract,
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
        status_options = {
            'all': {'label': 'All', 'domain': []},
            'draft': {'label': 'Draft', 'domain': [('state', '=', 'draft')]},
            'under_review': {'label': 'Under Review', 'domain': [('state', '=', 'under_review')]},
            'approved': {'label': 'Approved', 'domain': [('state', '=', 'approved')]},
            'done': {'label': 'Done', 'domain': [('state', '=', 'done')]},
            'cancelled': {'label': 'Cancelled', 'domain': [('state', '=', 'cancelled')]},
        }

        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        status_filter = kw.get('status_filter') or filterby or 'all'
        if status_filter not in status_options:
            status_filter = 'all'
        domain += status_options[status_filter]['domain']

        project_option_records = ConstructionIPC.search([]).mapped('contract_id.project_id').filtered(lambda p: p.id)
        project_options = [{'value': 'all', 'label': 'All Projects'}]
        for project in project_option_records.sorted(lambda p: (p.name or '').lower()):
            project_options.append({'value': str(project.id), 'label': project.name})

        project_filter = (kw.get('project_filter') or 'all').strip()
        if project_filter != 'all' and project_filter.isdigit():
            domain.append(('contract_id.project_id', '=', int(project_filter)))
        else:
            project_filter = 'all'

        ipc_count = ConstructionIPC.search_count(domain)

        pager = portal_pager(
            url="/my/employee/ipcs",
            url_args={'sortby': sortby, 'status_filter': status_filter, 'project_filter': project_filter},
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
            'status_options': status_options,
            'project_options': project_options,
            'sortby': sortby,
            'status_filter': status_filter,
            'project_filter': project_filter,
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
        status_options = {
            'all': {'label': 'All', 'domain': []},
            'draft': {'label': 'Draft', 'domain': [('state', '=', 'draft')]},
            'submitted': {'label': 'Submitted', 'domain': [('state', '=', 'submitted')]},
            'approved': {'label': 'Approved', 'domain': [('state', '=', 'approved')]},
            'rejected': {'label': 'Rejected', 'domain': [('state', '=', 'rejected')]},
        }

        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        status_filter = kw.get('status_filter') or filterby or 'all'
        if status_filter not in status_options:
            status_filter = 'all'
        domain += status_options[status_filter]['domain']

        project_option_records = ConstructionVariation.search([]).mapped('contract_id.project_id').filtered(lambda p: p.id)
        project_options = [{'value': 'all', 'label': 'All Projects'}]
        for project in project_option_records.sorted(lambda p: (p.name or '').lower()):
            project_options.append({'value': str(project.id), 'label': project.name})

        project_filter = (kw.get('project_filter') or 'all').strip()
        if project_filter != 'all' and project_filter.isdigit():
            domain.append(('contract_id.project_id', '=', int(project_filter)))
        else:
            project_filter = 'all'

        variation_count = ConstructionVariation.search_count(domain)
        
        pager = portal_pager(
            url="/my/employee/variations",
            url_args={'sortby': sortby, 'status_filter': status_filter, 'project_filter': project_filter},
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
            'status_options': status_options,
            'project_options': project_options,
            'sortby': sortby,
            'status_filter': status_filter,
            'project_filter': project_filter,
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
            'boq_lines': variation_sudo.contract_id.boq_line_ids.sorted(lambda l: (l.sequence, l.id)),
            'uoms': request.env['uom.uom'].sudo().search([]),
            'line_types': [
                ('increase', 'Quantity Increase'),
                ('decrease', 'Quantity Decrease'),
                ('new', 'New Item'),
                ('omit', 'Omit Item'),
                ('rate', 'Rate Change'),
            ],
            'success': request.params.get('success'),
            'error': request.params.get('error'),
            'page_name': 'construction_variation',
        }
        return request.render("construction_contract_management.portal_employee_variation_detail", values)

    @http.route(['/my/employee/variation/<int:variation_id>/add_line'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_variation_add_line(self, variation_id, **post):
        try:
            allowed_contract_ids = request.env['construction.contract'].search(self._portal_visible_contract_domain()).ids
            variation = request.env['construction.variation'].search([
                ('id', '=', variation_id),
                ('contract_id', 'in', allowed_contract_ids),
            ], limit=1)
            if not variation.exists():
                return request.redirect('/my/employee/variations')

            if variation.state != 'draft':
                return request.redirect(f'/my/employee/variation/{variation_id}')

            action = post.get('action', 'save')
            line_type = (post.get('type') or '').strip()
            boq_line_id = int(post.get('boq_line_id')) if post.get('boq_line_id') else False
            boq_line = request.env['construction.contract.boq.line'].sudo().browse(boq_line_id) if boq_line_id else False

            if action == 'submit' and not post.get('type') and variation.line_ids:
                variation.action_submit()
                return request.redirect(f'/my/employee/variation/{variation_id}?success=submitted')

            vals = {
                'variation_id': variation.id,
                'type': line_type,
                'boq_line_id': boq_line.id if boq_line else False,
                'section': (post.get('section') or '').strip(),
                'item_code': (post.get('item_code') or '').strip(),
                'description': (post.get('line_description') or '').strip(),
                'uom_id': int(post.get('uom_id')) if post.get('uom_id') else False,
                'unit_rate': float(post.get('unit_rate') or 0.0),
                'variation_qty': float(post.get('variation_qty') or 0.0),
            }

            if boq_line:
                vals['section'] = vals['section'] or boq_line.section or False
                vals['item_code'] = vals['item_code'] or boq_line.item_code or False
                vals['description'] = vals['description'] or boq_line.description or False
                vals['uom_id'] = vals['uom_id'] or boq_line.uom_id.id or False
                vals['unit_rate'] = float(post.get('unit_rate') or boq_line.unit_rate or 0.0)

            if line_type != 'new' and not boq_line:
                return request.redirect(f'/my/employee/variation/{variation_id}?error=boq_required')

            request.env['construction.variation.line'].sudo().create(vals)

            if action == 'submit':
                variation.action_submit()
                return request.redirect(f'/my/employee/variation/{variation_id}?success=submitted')

            return request.redirect(f'/my/employee/variation/{variation_id}?success=saved')
        except (ValidationError, ValueError):
            return request.redirect(f'/my/employee/variation/{variation_id}?error=validation')
        except Exception:
            return request.redirect(f'/my/employee/variation/{variation_id}?error=system')

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
        status_options = {
            'all': {'label': 'All', 'domain': []},
            'draft': {'label': 'Draft', 'domain': [('state', '=', 'draft')]},
            'submitted': {'label': 'Submitted', 'domain': [('state', '=', 'submitted')]},
            'checked': {'label': 'Checked', 'domain': [('state', '=', 'checked')]},
            'approved': {'label': 'Approved', 'domain': [('state', '=', 'approved')]},
            'rejected': {'label': 'Rejected', 'domain': [('state', '=', 'rejected')]},
        }

        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        status_filter = kw.get('status_filter') or filterby or 'all'
        if status_filter not in status_options:
            status_filter = 'all'
        domain += status_options[status_filter]['domain']

        project_option_records = ConstructionMeasurement.search([]).mapped('contract_id.project_id').filtered(lambda p: p.id)
        project_options = [{'value': 'all', 'label': 'All Projects'}]
        for project in project_option_records.sorted(lambda p: (p.name or '').lower()):
            project_options.append({'value': str(project.id), 'label': project.name})

        project_filter = (kw.get('project_filter') or 'all').strip()
        if project_filter != 'all' and project_filter.isdigit():
            domain.append(('contract_id.project_id', '=', int(project_filter)))
        else:
            project_filter = 'all'

        measurement_count = ConstructionMeasurement.search_count(domain)
        
        pager = portal_pager(
            url="/my/employee/measurements",
            url_args={'sortby': sortby, 'status_filter': status_filter, 'project_filter': project_filter},
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
            'status_options': status_options,
            'project_options': project_options,
            'sortby': sortby,
            'status_filter': status_filter,
            'project_filter': project_filter,
        })
        return request.render("construction_contract_management.portal_employee_measurements", values)

# ---------------------------------------------------------
    # CONSTRUCTION - MEASUREMENT DETAIL (with BOQ for editing)
    # ---------------------------------------------------------
    @http.route(['/my/employee/measurement/<int:measurement_id>'], type='http', auth='user', website=True)
    def portal_construction_measurement_detail(self, measurement_id, **kw):
        try:
            error = request.params.get('error')
            success = request.params.get('success')
            allowed_contract_ids = request.env['construction.contract'].search(self._portal_visible_contract_domain()).ids
            measurement = request.env['construction.measurement'].search([
                ('id', '=', measurement_id),
                ('contract_id', 'in', allowed_contract_ids),
            ], limit=1)

            if not measurement.exists():
                return request.redirect('/my/employee/measurements')

            contract = measurement.contract_id
            boq_lines = contract.boq_line_ids.sorted(lambda l: (l.sequence, l.id))
            MeasurementLine = request.env['construction.measurement.line']

            existing_lines = {}
            for line in measurement.line_ids:
                if line.boq_line_id:
                    existing_lines[line.boq_line_id.id] = line

            previous_qty_map = {}
            for boq_line in boq_lines:
                approved_lines = MeasurementLine.search([
                    ('boq_line_id', '=', boq_line.id),
                    ('measurement_id.contract_id', '=', contract.id),
                    ('measurement_id.state', '=', 'approved'),
                    ('measurement_id', '!=', measurement.id),
                ])
                previous_qty_map[boq_line.id] = sum(approved_lines.mapped('current_qty'))

            contract_revised = contract.revised_amount or sum(contract.boq_line_ids.mapped('revised_amount')) or sum(contract.boq_line_ids.mapped('total_amount')) or contract.original_amount or 0.0

            approved_measurement_lines = MeasurementLine.search([
                ('measurement_id.contract_id', '=', contract.id),
                ('measurement_id.state', '=', 'approved'),
            ])
            contract_certified = sum(
                (line.current_qty or 0.0) * (line.boq_line_id.revised_unit_rate or line.boq_line_id.unit_rate or 0.0)
                for line in approved_measurement_lines
            )

            values = self._prepare_portal_layout_values()
            values.update({
                'measurement': measurement,
                'boq_lines': boq_lines,
                'existing_lines': existing_lines,
                'previous_qty_map': previous_qty_map,
                'contract_revised': contract_revised,
                'contract_certified': contract_certified,
                'error': error,
                'success': success,
                'page_name': 'construction_measurement',
            })
            return request.render("construction_contract_management.portal_employee_measurement_detail", values)

        except Exception as e:
            return request.redirect('/my/employee/measurements')

    # ---------------------------------------------------------
    # CONSTRUCTION - ADD MEASUREMENT LINES
    # ---------------------------------------------------------
    @http.route(['/my/employee/measurement/<int:measurement_id>/add_lines'], 
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_measurement_add_lines(self, measurement_id, **post):
        try:
            allowed_contract_ids = request.env['construction.contract'].search(self._portal_visible_contract_domain()).ids
            measurement = request.env['construction.measurement'].search([
                ('id', '=', measurement_id),
                ('contract_id', 'in', allowed_contract_ids),
            ], limit=1)

            if not measurement.exists():
                return request.redirect('/my/employee/measurements')

            if measurement.state != 'draft':
                return request.redirect(f'/my/employee/measurement/{measurement_id}')

            boq_lines = measurement.contract_id.boq_line_ids.sorted(lambda l: (l.sequence, l.id))
            MeasurementLine = request.env['construction.measurement.line'].sudo()
            validation_errors = []

            for boq_line in boq_lines:
                qty_str = (post.get(f'qty_{boq_line.id}') or '0').strip()
                qty_percent_str = (post.get(f'qty_percent_{boq_line.id}') or '').strip()
                remarks = (post.get(f'remarks_{boq_line.id}') or '').strip()
                allowed_qty = boq_line.revised_qty or boq_line.contract_qty or 0.0

                try:
                    current_qty = float(qty_str)
                except (ValueError, TypeError):
                    current_qty = 0.0

                try:
                    qty_percent = float(qty_percent_str) if qty_percent_str else None
                except (ValueError, TypeError):
                    qty_percent = None

                if qty_percent is not None and allowed_qty:
                    current_qty = (allowed_qty * qty_percent) / 100.0

                existing_line = MeasurementLine.search([
                    ('measurement_id', '=', measurement.id),
                    ('boq_line_id', '=', boq_line.id),
                ], limit=1)

                approved_lines = MeasurementLine.search([
                    ('boq_line_id', '=', boq_line.id),
                    ('measurement_id.contract_id', '=', measurement.contract_id.id),
                    ('measurement_id.state', '=', 'approved'),
                    ('measurement_id', '!=', measurement.id),
                ])

                previous_qty = sum(approved_lines.mapped('current_qty'))
                cumulative_qty = previous_qty + current_qty

                if current_qty > 0 and allowed_qty and cumulative_qty > allowed_qty:
                    label = boq_line.item_code or (boq_line.description or '')[:30]
                    validation_errors.append(
                        f"{label}: cumulative {cumulative_qty:.2f} exceeds allowed {allowed_qty:.2f}"
                    )
                    continue

                line_vals = {
                    'measurement_id': measurement.id,
                    'boq_line_id': boq_line.id,
                    'previous_qty': previous_qty,
                    'current_qty': current_qty,
                    'remarks': remarks or False,
                }

                if current_qty > 0:
                    if existing_line:
                        existing_line.write(line_vals)
                    else:
                        MeasurementLine.create(line_vals)
                elif existing_line:
                    existing_line.unlink()

            if validation_errors:
                message = "Some quantities could not be saved:<br/>" + "<br/>".join(validation_errors)
                measurement.message_post(body=message, message_type='comment')
                return request.redirect(f'/my/employee/measurement/{measurement_id}?error=validation')

            action = post.get('action', 'save')
            measurement = request.env['construction.measurement'].search([
                ('id', '=', measurement_id),
                ('contract_id', 'in', allowed_contract_ids),
            ], limit=1)
            measurement.contract_id.boq_line_ids._compute_progress_fields()
            measurement.contract_id._compute_summary_amounts()
            positive_lines = measurement.line_ids.filtered(lambda l: l.current_qty > 0)

            if action == 'submit':
                if not positive_lines:
                    return request.redirect(f'/my/employee/measurement/{measurement_id}?error=no_lines')

                measurement.action_submit()
                measurement.message_post(
                    body=f"Measurement submitted for approval by {request.env.user.name}",
                    message_type='notification',
                )
                return request.redirect(f'/my/employee/measurement/{measurement_id}?success=submitted')

            return request.redirect(f'/my/employee/measurement/{measurement_id}?success=saved')

        except Exception as e:
            return request.redirect(f'/my/employee/measurement/{measurement_id}?error=system')

   # ---------------------------------------------------------
    # CONSTRUCTION - NEW MEASUREMENT FORM (FIXED)
    # ---------------------------------------------------------
    @http.route(['/my/employee/measurement/new'], type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_construction_measurement_new(self, **post):
        user = request.env.user

        if not request.env['construction.measurement'].check_access_rights('create', raise_exception=False):
            return request.redirect("/my/employee")

        def _measurement_new_values(error_message=None):
            try:
                contracts = request.env['construction.contract'].search(
                    [('state', 'in', ['active', 'approved'])] + self._portal_visible_contract_domain()
                )
            except Exception:
                contracts = request.env['construction.contract']
            return {
                'contracts': contracts,
                'page_name': 'construction_measurement_new',
                'error_message': error_message,
            }

        if request.httprequest.method == 'POST':
            try:
                allowed_contract_ids = request.env['construction.contract'].search(self._portal_visible_contract_domain()).ids
                contract_id = int(post.get('contract_id'))
                if contract_id not in allowed_contract_ids:
                    return request.render(
                        "construction_contract_management.portal_employee_measurement_new",
                        _measurement_new_values("You are not allowed to create a measurement for this contract.")
                    )

                vals = {
                    'contract_id': contract_id,
                    'date': post.get('date') or False,
                    'period_from': post.get('period_from') or False,
                    'period_to': post.get('period_to') or False,
                }

                measurement = request.env['construction.measurement'].sudo().create(vals)
                measurement.action_load_boq_lines()
                return request.redirect(f'/my/employee/measurement/{measurement.id}')
            except Exception:
                return request.render(
                    "construction_contract_management.portal_employee_measurement_new",
                    _measurement_new_values("Could not create the measurement. Please check the entered data and try again.")
                )

        return request.render("construction_contract_management.portal_employee_measurement_new", _measurement_new_values())

    # ---------------------------------------------------------
    # CONSTRUCTION - NEW VARIATION FORM (FIXED)
    # ---------------------------------------------------------
    @http.route(['/my/employee/variation/new'], type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_construction_variation_new(self, **post):
        user = request.env.user

        if not request.env['construction.variation'].check_access_rights('create', raise_exception=False):
            return request.redirect("/my/employee")

        def _variation_new_values(error_message=None):
            try:
                contracts = request.env['construction.contract'].search(
                    [('state', 'in', ['active', 'approved'])] + self._portal_visible_contract_domain()
                )
            except Exception:
                contracts = request.env['construction.contract']
            return {
                'contracts': contracts,
                'page_name': 'construction_variation_new',
                'error_message': error_message,
            }

        if request.httprequest.method == 'POST':
            allowed_contract_ids = request.env['construction.contract'].search(self._portal_visible_contract_domain()).ids
            contract_id = int(post.get('contract_id'))
            if contract_id not in allowed_contract_ids:
                return request.render(
                    "construction_contract_management.portal_employee_variation_new",
                    _variation_new_values("You are not allowed to create a variation for this contract.")
                )

            vals = {
                'contract_id': contract_id,
                'date': post.get('date'),
                'description': post.get('description', ''),  # Variation DOES have description field
            }
            
            # Add reason to description if provided
            if post.get('reason'):
                vals['description'] = vals['description'] + '\n\nReason: ' + post.get('reason')
            
            try:
                variation = request.env['construction.variation'].create(vals)
                return request.redirect(f'/my/employee/variation/{variation.id}')
            except Exception:
                return request.render(
                    "construction_contract_management.portal_employee_variation_new",
                    _variation_new_values("Could not create the variation. Please check the entered data and try again.")
                )

        return request.render("construction_contract_management.portal_employee_variation_new", _variation_new_values())
