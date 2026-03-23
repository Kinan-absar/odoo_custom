import base64
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager  # FIXED: Added pager import
from odoo.exceptions import AccessError, MissingError, ValidationError
import logging

_logger = logging.getLogger(__name__)


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
    def portal_employee_measurements(self, page=1, **kw):
        Measurement = request.env['construction.measurement']
        measurement_count = Measurement.search_count([])
        
        pager = portal_pager(
            url="/my/employee/measurements",
            total=measurement_count,
            page=page,
            step=self._items_per_page
        )
        
        measurements = Measurement.search([], order='id desc', limit=self._items_per_page, offset=pager['offset'])
        
        values = {
            'measurements': measurements,
            'pager': pager,
            'page_name': 'construction_measurements',
        }
        return request.render("construction_contract_management.portal_employee_measurements", values)

    @http.route(['/my/employee/measurement/new'], type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_construction_measurement_new(self, **post):
        if request.httprequest.method == 'POST':
            vals = {
                'contract_id': int(post.get('contract_id')),
                'date': post.get('date'),
                'period_from': post.get('period_from'),
                'period_to': post.get('period_to'),
            }
            measurement = request.env['construction.measurement'].create(vals)
            return request.redirect(f'/my/employee/measurement/{measurement.id}')
        
        contracts = request.env['construction.contract'].search([('state', 'in', ['active', 'approved'])])
        values = {
            'contracts': contracts,
            'page_name': 'construction_measurement_new',
        }
        return request.render("construction_contract_management.portal_employee_measurement_new", values)

    @http.route(['/my/employee/measurement/<int:measurement_id>'], type='http', auth='user', website=True)
    def portal_construction_measurement_detail(self, measurement_id, **kw):
        try:
            measurement = request.env['construction.measurement'].browse(measurement_id)
            
            if not measurement.exists():
                return request.redirect('/my/employee/measurements')
            
            boq_lines = measurement.contract_id.boq_line_ids
            
            existing_lines = {}
            for line in measurement.line_ids:
                existing_lines[line.boq_line_id.id] = line
            
            # Build previous quantity map
            MeasurementLine = request.env['construction.measurement.line']
            previous_qty_map = {}
            
            for boq_line in boq_lines:
                last_line = MeasurementLine.search([
                    ('boq_line_id', '=', boq_line.id),
                    ('measurement_id.contract_id', '=', measurement.contract_id.id),
                    ('measurement_id.state', '=', 'approved'),
                    ('measurement_id', '!=', measurement.id),
                ], order='measurement_id.id desc, id desc', limit=1)
                
                previous_qty_map[boq_line.id] = last_line.cumulative_qty if last_line else 0.0
            
            # Calculate progress
            contract = measurement.contract_id
            contract_revised = contract.revised_amount or contract.original_amount or 0.0
            
            approved_total = 0.0
            approved_measurements = request.env['construction.measurement'].search([
                ('contract_id', '=', contract.id),
                ('state', '=', 'approved'),
            ])
            
            for meas in approved_measurements:
                for line in meas.line_ids:
                    approved_total += (line.current_qty or 0.0) * (line.unit_rate or 0.0)
            
            values = {
                'measurement': measurement,
                'boq_lines': boq_lines,
                'existing_lines': existing_lines,
                'previous_qty_map': previous_qty_map,
                'contract_revised': contract_revised,
                'contract_certified': approved_total,
                'error': kw.get('error'),
                'success': kw.get('success'),
                'page_name': 'construction_measurement',
            }
            
            return request.render("construction_contract_management.portal_employee_measurement_detail", values)
            
        except Exception as e:
            _logger.error(f"Error in measurement detail: {str(e)}", exc_info=True)
            return request.redirect('/my/employee/measurements')

    @http.route(['/my/employee/measurement/<int:measurement_id>/add_lines'], 
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_measurement_add_lines(self, measurement_id, **post):
        try:
            measurement = request.env['construction.measurement'].browse(measurement_id)
            
            if not measurement.exists() or measurement.state != 'draft':
                return request.redirect(f'/my/employee/measurement/{measurement_id}?error=state')
            
            boq_lines = measurement.contract_id.boq_line_ids
            MeasurementLine = request.env['construction.measurement.line']
            
            validation_errors = []
            lines_processed = 0
            
            for boq_line in boq_lines:
                qty_str = post.get(f'qty_{boq_line.id}', '0').strip()
                try:
                    current_qty = float(qty_str) if qty_str else 0.0
                except ValueError:
                    current_qty = 0.0
                
                existing_line = MeasurementLine.search([
                    ('measurement_id', '=', measurement.id),
                    ('boq_line_id', '=', boq_line.id),
                ], limit=1)
                
                last_approved = MeasurementLine.search([
                    ('boq_line_id', '=', boq_line.id),
                    ('measurement_id.contract_id', '=', measurement.contract_id.id),
                    ('measurement_id.state', '=', 'approved'),
                    ('measurement_id', '!=', measurement.id),
                ], order='measurement_id.id desc', limit=1)
                
                previous_qty = last_approved.cumulative_qty if last_approved else 0.0
                remarks = post.get(f'remarks_{boq_line.id}', '').strip()
                
                line_vals = {
                    'measurement_id': measurement.id,
                    'boq_line_id': boq_line.id,
                    'previous_qty': previous_qty,
                    'current_qty': current_qty,
                    'remarks': remarks if remarks else False,
                }
                
                cumulative = previous_qty + current_qty
                allowed = boq_line.revised_qty or boq_line.contract_qty
                
                if current_qty > 0:
                    if cumulative > allowed:
                        validation_errors.append({
                            'item': boq_line.item_code or boq_line.description[:30],
                            'cumulative': cumulative,
                            'allowed': allowed,
                        })
                    
                    try:
                        if existing_line:
                            existing_line.write(line_vals)
                        else:
                            MeasurementLine.create(line_vals)
                        lines_processed += 1
                    except ValidationError as ve:
                        validation_errors.append({
                            'item': boq_line.item_code or boq_line.description[:30],
                            'error': str(ve),
                        })
                else:
                    if existing_line:
                        existing_line.sudo().unlink()
            
            if validation_errors:
                error_msg = "Cannot save - quantities exceed allowed:\n"
                for err in validation_errors:
                    if 'error' in err:
                        error_msg += f"{err['item']}: {err['error']}\n"
                    else:
                        error_msg += f"{err['item']}: {err['cumulative']:.2f} > {err['allowed']:.2f}\n"
                
                measurement.message_post(body=error_msg, message_type='comment')
                return request.redirect(f'/my/employee/measurement/{measurement_id}?error=validation')
            
            try:
                photos = request.httprequest.files.getlist('photos')
                if photos:
                    IrAttachment = request.env['ir.attachment']
                    for photo in photos:
                        if photo and photo.filename:
                            file_content = photo.read()
                            IrAttachment.sudo().create({
                                'name': photo.filename,
                                'type': 'binary',
                                'datas': base64.b64encode(file_content),
                                'res_model': 'construction.measurement',
                                'res_id': measurement.id,
                                'mimetype': photo.content_type or 'image/jpeg',
                            })
            except Exception as e:
                _logger.error(f"Photo upload error: {str(e)}")
            
            action = post.get('action', 'save')
            
            if action == 'submit' and measurement.line_ids:
                try:
                    measurement.action_submit()
                    measurement.message_post(
                        body=f"Measurement submitted for approval by {request.env.user.name}",
                        message_type='notification',
                    )
                    return request.redirect(f'/my/employee/measurement/{measurement_id}?success=submitted')
                except Exception as e:
                    _logger.error(f"Submit failed: {str(e)}")
                    try:
                        measurement.sudo().write({'state': 'submitted'})
                        return request.redirect(f'/my/employee/measurement/{measurement_id}?success=submitted')
                    except Exception as e2:
                        _logger.error(f"Submit with sudo failed: {str(e2)}")
                        return request.redirect(f'/my/employee/measurement/{measurement_id}?error=submit')
            
            return request.redirect(f'/my/employee/measurement/{measurement_id}?success=saved')
            
        except Exception as e:
            _logger.error(f"Error saving measurement: {str(e)}", exc_info=True)
            return request.redirect(f'/my/employee/measurement/{measurement_id}?error=system')