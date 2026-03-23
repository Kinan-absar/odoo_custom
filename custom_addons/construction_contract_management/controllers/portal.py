import base64
import logging

from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError, ValidationError

_logger = logging.getLogger(__name__)


class ConstructionPortalEmployeeSuite(CustomerPortal):

    # =========================================================
    # CONTRACTS
    # =========================================================
    @http.route(['/my/employee/contracts', '/my/employee/contracts/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_employee_contracts(self, page=1, sortby=None, filterby=None, **kw):
        values = self._prepare_portal_layout_values()
        ConstructionContract = request.env['construction.contract'].sudo()

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

        sortby = sortby or 'date'
        filterby = filterby or 'all'
        order = searchbar_sortings[sortby]['order']
        domain = list(searchbar_filters[filterby]['domain'])

        contract_count = ConstructionContract.search_count(domain)
        pager = portal_pager(
            url="/my/employee/contracts",
            url_args={'sortby': sortby, 'filterby': filterby},
            total=contract_count,
            page=page,
            step=self._items_per_page,
        )

        contracts = ConstructionContract.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset'],
        )

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
        try:
            contract_sudo = self._document_check_access('construction.contract', contract_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        return request.render("construction_contract_management.portal_employee_contract_detail", {
            'contract': contract_sudo,
            'page_name': 'construction_contract',
        })

    # =========================================================
    # IPCs
    # =========================================================
    @http.route(['/my/employee/ipcs', '/my/employee/ipcs/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_employee_ipcs(self, page=1, sortby=None, filterby=None, **kw):
        values = self._prepare_portal_layout_values()
        ConstructionIPC = request.env['construction.ipc'].sudo()

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

        sortby = sortby or 'date'
        filterby = filterby or 'all'
        order = searchbar_sortings[sortby]['order']
        domain = list(searchbar_filters[filterby]['domain'])

        ipc_count = ConstructionIPC.search_count(domain)
        pager = portal_pager(
            url="/my/employee/ipcs",
            url_args={'sortby': sortby, 'filterby': filterby},
            total=ipc_count,
            page=page,
            step=self._items_per_page,
        )

        ipcs = ConstructionIPC.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset'],
        )

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
        try:
            ipc_sudo = self._document_check_access('construction.ipc', ipc_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        if report_type in ('html', 'pdf', 'text'):
            return self._show_report(
                model=ipc_sudo,
                report_type=report_type,
                report_ref='construction_contract_management.action_report_construction_ipc',
                download=download,
            )

        return request.render("construction_contract_management.portal_employee_ipc_detail", {
            'ipc': ipc_sudo,
            'page_name': 'construction_ipc',
        })

    # =========================================================
    # VARIATIONS
    # =========================================================
    @http.route(['/my/employee/variations', '/my/employee/variations/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_employee_variations(self, page=1, sortby=None, filterby=None, **kw):
        values = self._prepare_portal_layout_values()
        ConstructionVariation = request.env['construction.variation'].sudo()

        searchbar_sortings = {
            'date': {'label': 'Newest', 'order': 'id desc'},
            'name': {'label': 'Reference', 'order': 'name'},
        }
        searchbar_filters = {
            'all': {'label': 'All', 'domain': []},
            'draft': {'label': 'Draft', 'domain': [('state', '=', 'draft')]},
            'submitted': {'label': 'Submitted', 'domain': [('state', '=', 'submitted')]},
            'under_review': {'label': 'Under Review', 'domain': [('state', '=', 'under_review')]},
            'approved': {'label': 'Approved', 'domain': [('state', '=', 'approved')]},
        }

        sortby = sortby or 'date'
        filterby = filterby or 'all'
        order = searchbar_sortings[sortby]['order']
        domain = list(searchbar_filters[filterby]['domain'])

        variation_count = ConstructionVariation.search_count(domain)
        pager = portal_pager(
            url="/my/employee/variations",
            url_args={'sortby': sortby, 'filterby': filterby},
            total=variation_count,
            page=page,
            step=self._items_per_page,
        )

        variations = ConstructionVariation.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset'],
        )

        values.update({
            'variations': variations,
            'page_name': 'construction_variation',
            'default_url': '/my/employee/variations',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': searchbar_filters,
            'sortby': sortby,
            'filterby': filterby,
        })
        return request.render("construction_contract_management.portal_employee_variations", values)

    @http.route(['/my/employee/variation/<int:variation_id>'], type='http', auth='user', website=True)
    def portal_employee_variation_detail(self, variation_id, access_token=None, **kw):
        try:
            variation_sudo = self._document_check_access('construction.variation', variation_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my/employee')

        return request.render("construction_contract_management.portal_employee_variation_detail", {
            'variation': variation_sudo,
            'page_name': 'construction_variation',
        })

    # =========================================================
    # MEASUREMENTS LIST
    # =========================================================
    @http.route(['/my/employee/measurements', '/my/employee/measurements/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_employee_measurements(self, page=1, **kw):
        values = self._prepare_portal_layout_values()
        Measurement = request.env['construction.measurement'].sudo()

        measurement_count = Measurement.search_count([])
        pager = portal_pager(
            url="/my/employee/measurements",
            total=measurement_count,
            page=page,
            step=self._items_per_page,
        )

        measurements = Measurement.search(
            [],
            order='id desc',
            limit=self._items_per_page,
            offset=pager['offset'],
        )

        values.update({
            'measurements': measurements,
            'pager': pager,
            'page_name': 'construction_measurements',
        })
        return request.render("construction_contract_management.portal_employee_measurements", values)

    # =========================================================
    # NEW MEASUREMENT
    # =========================================================
    @http.route(['/my/employee/measurement/new'], type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_construction_measurement_new(self, **post):
        if request.httprequest.method == 'POST':
            try:
                contract_id = int(post.get('contract_id'))
                vals = {
                    'contract_id': contract_id,
                    'date': post.get('date') or False,
                    'period_from': post.get('period_from') or False,
                    'period_to': post.get('period_to') or False,
                }

                measurement = request.env['construction.measurement'].sudo().create(vals)

                # preload lines the same way your model is designed to work
                try:
                    measurement.action_load_boq_lines()
                except Exception as e:
                    _logger.warning("Could not preload BOQ lines on measurement %s: %s", measurement.id, str(e))

                return request.redirect(f'/my/employee/measurement/{measurement.id}')

            except Exception as e:
                _logger.error("Error creating measurement: %s", str(e), exc_info=True)
                contracts = request.env['construction.contract'].sudo().search([('state', 'in', ['active', 'approved'])])
                return request.render("construction_contract_management.portal_employee_measurement_new", {
                    'contracts': contracts,
                    'page_name': 'construction_measurement_new',
                    'error': 'create_failed',
                })

        contracts = request.env['construction.contract'].sudo().search([('state', 'in', ['active', 'approved'])])
        return request.render("construction_contract_management.portal_employee_measurement_new", {
            'contracts': contracts,
            'page_name': 'construction_measurement_new',
        })

    # =========================================================
    # MEASUREMENT DETAIL
    # =========================================================
    @http.route(['/my/employee/measurement/<int:measurement_id>'], type='http', auth='user', website=True)
    def portal_construction_measurement_detail(self, measurement_id, **kw):
        error = request.params.get('error')
        success = request.params.get('success')

        measurement = request.env['construction.measurement'].sudo().browse(measurement_id)
        if not measurement.exists():
            return request.redirect('/my/employee/measurements')

        contract = measurement.contract_id.sudo()
        boq_lines = contract.boq_line_ids.sorted(lambda l: (l.sequence, l.id))
        MeasurementLine = request.env['construction.measurement.line'].sudo()

        # existing saved lines for this measurement
        existing_lines = {}
        for line in measurement.line_ids:
            if line.boq_line_id:
                existing_lines[line.boq_line_id.id] = line

        # previous qty from latest approved measurement line for same contract + boq line
        previous_qty_map = {}
        for boq_line in boq_lines:
            approved_lines = MeasurementLine.search([
                ('boq_line_id', '=', boq_line.id),
                ('measurement_id.contract_id', '=', contract.id),
                ('measurement_id.state', '=', 'approved'),
                ('measurement_id', '!=', measurement.id),
            ])

            previous_qty_map[boq_line.id] = sum(approved_lines.mapped('current_qty'))

        # progress denominator
        contract_revised = contract.revised_amount or sum(contract.boq_line_ids.mapped('revised_amount')) or sum(contract.boq_line_ids.mapped('total_amount')) or contract.original_amount or 0.0

        # progress numerator:
        # prefer contract computed measured amount if available, otherwise compute from approved measurements
        contract_certified = contract.total_measured_amount or sum(
            (line.measured_qty or 0.0) * (line.revised_unit_rate or line.unit_rate or 0.0)
            for line in contract.boq_line_ids
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

    # =========================================================
    # SAVE / SUBMIT MEASUREMENT LINES
    # =========================================================
    @http.route(['/my/employee/measurement/<int:measurement_id>/add_lines'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_measurement_add_lines(self, measurement_id, **post):
        try:
            measurement = request.env['construction.measurement'].sudo().browse(measurement_id)

            if not measurement.exists():
                return request.redirect('/my/employee/measurements')

            if measurement.state != 'draft':
                return request.redirect(f'/my/employee/measurement/{measurement_id}')

            boq_lines = measurement.contract_id.boq_line_ids.sorted(lambda l: (l.sequence, l.id))
            MeasurementLine = request.env['construction.measurement.line'].sudo()
            validation_errors = []

            for boq_line in boq_lines:
                qty_str = (post.get(f'qty_{boq_line.id}') or '0').strip()
                remarks = (post.get(f'remarks_{boq_line.id}') or '').strip()

                try:
                    current_qty = float(qty_str)
                except (ValueError, TypeError):
                    current_qty = 0.0

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
                allowed_qty = boq_line.revised_qty or boq_line.contract_qty or 0.0
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

                try:
                    if current_qty > 0:
                        if existing_line:
                            existing_line.write(line_vals)
                        else:
                            MeasurementLine.create(line_vals)
                    else:
                        if existing_line:
                            existing_line.unlink()
                except ValidationError as ve:
                    label = boq_line.item_code or (boq_line.description or '')[:30]
                    validation_errors.append(f"{label}: {str(ve)}")

            if validation_errors:
                message = "Some quantities could not be saved:<br/>" + "<br/>".join(validation_errors)
                measurement.message_post(body=message, message_type='comment')
                return request.redirect(f'/my/employee/measurement/{measurement_id}?error=validation')

            # photo upload
            try:
                for photo in request.httprequest.files.getlist('photos'):
                    if photo and photo.filename:
                        request.env['ir.attachment'].sudo().create({
                            'name': photo.filename,
                            'type': 'binary',
                            'datas': base64.b64encode(photo.read()),
                            'res_model': 'construction.measurement',
                            'res_id': measurement.id,
                            'mimetype': photo.content_type or 'image/jpeg',
                        })
            except Exception as e:
                _logger.error("Photo upload error on measurement %s: %s", measurement.id, str(e), exc_info=True)

            action = post.get('action', 'save')

            # re-browse after create/write/unlink to get fresh line_ids
            measurement = request.env['construction.measurement'].sudo().browse(measurement_id)
            positive_lines = measurement.line_ids.filtered(lambda l: l.current_qty > 0)

            if action == 'submit':
                if not positive_lines:
                    return request.redirect(f'/my/employee/measurement/{measurement_id}?error=no_lines')

                try:
                    measurement.action_submit()
                except Exception as e:
                    _logger.warning("action_submit failed on measurement %s, fallback write used: %s", measurement.id, str(e))
                    measurement.write({'state': 'submitted'})

                measurement.message_post(
                    body=f"Measurement submitted for approval by {request.env.user.name}",
                    message_type='notification',
                )
                return request.redirect(f'/my/employee/measurement/{measurement_id}?success=submitted')

            return request.redirect(f'/my/employee/measurement/{measurement_id}?success=saved')

        except Exception as e:
            _logger.error("Error saving measurement lines for %s: %s", measurement_id, str(e), exc_info=True)
            return request.redirect(f'/my/employee/measurement/{measurement_id}?error=system')
