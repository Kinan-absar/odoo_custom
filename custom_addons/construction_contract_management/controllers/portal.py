from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError


class ConstructionPortalEmployeeSuite(CustomerPortal):

    # ========== CONTRACTS ==========
    @http.route(['/my/employee/contracts', '/my/employee/contracts/page/<int:page>'], 
                type='http', auth='user', website=True)
    def portal_employee_contracts(self, page=1, sortby=None, filterby=None, **kw):
        """List all construction contracts"""
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
    def portal_employee_contract_detail(self, contract_id, access_token=None, **kw):
        """View contract details"""
        try:
            contract_sudo = self._document_check_access('construction.contract', contract_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        values = {
            'contract': contract_sudo,
            'page_name': 'construction_contract',
        }
        return request.render("construction_contract_management.portal_employee_contract_detail", values)

    # ========== IPCs ==========
    @http.route(['/my/employee/ipcs', '/my/employee/ipcs/page/<int:page>'], 
                type='http', auth='user', website=True)
    def portal_employee_ipcs(self, page=1, sortby=None, filterby=None, **kw):
        """List all IPCs"""
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
    def portal_employee_ipc_detail(self, ipc_id, access_token=None, report_type=None, download=False, **kw):
        """View IPC details or download PDF"""
        try:
            ipc_sudo = self._document_check_access('construction.ipc', ipc_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        if report_type in ('html', 'pdf', 'text'):
            return self._show_report(model=ipc_sudo, report_type=report_type, report_ref='construction_contract_management.action_report_construction_ipc', download=download)

        values = {
            'ipc': ipc_sudo,
            'page_name': 'construction_ipc',
        }
        return request.render("construction_contract_management.portal_employee_ipc_detail", values)

    # ========== VARIATIONS ==========
    @http.route(['/my/employee/variations', '/my/employee/variations/page/<int:page>'], 
                type='http', auth='user', website=True)
    def portal_employee_variations(self, page=1, sortby=None, filterby=None, **kw):
        """List all variations"""
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
    def portal_employee_variation_detail(self, variation_id, access_token=None, **kw):
        """View variation details"""
        try:
            variation_sudo = self._document_check_access('construction.variation', variation_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        values = {
            'variation': variation_sudo,
            'page_name': 'construction_variation',
        }
        return request.render("construction_contract_management.portal_employee_variation_detail", values)

    # ========== MEASUREMENTS ==========
    @http.route(['/my/employee/measurements', '/my/employee/measurements/page/<int:page>'], 
                type='http', auth='user', website=True)
    def portal_employee_measurements(self, page=1, sortby=None, filterby=None, **kw):
        """List all measurements"""
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
    def portal_employee_measurement_detail(self, measurement_id, access_token=None, **kw):
        """View measurement details"""
        try:
            measurement_sudo = self._document_check_access('construction.measurement', measurement_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        values = {
            'measurement': measurement_sudo,
            'page_name': 'construction_measurement',
        }
        return request.render("construction_contract_management.portal_employee_measurement_detail", values)
