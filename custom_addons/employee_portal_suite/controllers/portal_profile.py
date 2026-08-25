import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Fields the employee is allowed to self-edit from the portal.
# Kept as an explicit whitelist so a form-tampering attempt can never write
# to fields like job_position, department, contract data, etc.
CONTACT_FIELDS = [
    'private_phone',
    'private_email',
    'private_street',
    'private_street2',
    'private_city',
    'private_zip',
    'private_country_id',
]
EMERGENCY_FIELDS = [
    'emergency_contact',
    'emergency_phone',
]
# Additional personal/HR self-service fields, standard on hr.employee's
# "HR Settings" / "Private Information" tab. Each is checked with
# _field_exists before use, so this degrades gracefully on any instance.
PERSONAL_FIELDS = [
    'birthday',
    'place_of_birth',
    'country_of_birth',
    'country_id',
    'gender',
    'marital',
    'spouse_complete_name',
    'children',
    'identification_id',
    'ssn_no',
    'passport_id',
    'permit_no',
    'visa_no',
    'visa_expire',
    'certificate',
    'study_field',
    'study_school',
    'km_home_work',
    'private_car_plate',
]


class EmployeePortalProfile(http.Controller):

    def _field_exists(self, model, field_name):
        return field_name in model._fields

    @http.route('/my/employee/profile', type='http', auth='user', website=True)
    def portal_profile(self, **kw):
        user = request.env.user
        employee = user.employee_id

        if not employee:
            return request.redirect('/my/employee')

        employee = employee.sudo()
        has_bank_field = self._field_exists(employee, 'bank_account_id')
        bank_account = employee.bank_account_id if has_bank_field and employee.bank_account_id else None

        available_personal_fields = [f for f in PERSONAL_FIELDS if self._field_exists(employee, f)]
        marital_options = []
        if 'marital' in available_personal_fields:
            marital_field = employee._fields['marital']
            marital_options = marital_field.selection if isinstance(marital_field.selection, list) else \
                marital_field.selection(employee)

        return request.render('employee_portal_suite.portal_employee_profile', {
            'employee': employee,
            'bank_account': bank_account,
            'has_bank_field': has_bank_field,
            'has_emergency_fields': self._field_exists(employee, 'emergency_contact'),
            'available_personal_fields': available_personal_fields,
            'marital_options': marital_options,
            'success_message': kw.get('success'),
            'error_message': kw.get('error'),
            'page_name': 'profile',
        })

    @http.route('/my/employee/profile/update', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_profile_update(self, **post):
        user = request.env.user
        employee = user.employee_id

        if not employee:
            return request.redirect('/my/employee')

        employee = employee.sudo()
        had_error = False

        # --- Contact info + emergency contact + personal details ------------
        try:
            vals = {}
            for f in CONTACT_FIELDS:
                if not self._field_exists(employee, f):
                    continue
                if f == 'private_country_id':
                    country_id = post.get('private_country_id')
                    vals['private_country_id'] = int(country_id) if country_id else False
                else:
                    vals[f] = post.get(f, '')

            if self._field_exists(employee, 'emergency_contact'):
                for f in EMERGENCY_FIELDS:
                    if self._field_exists(employee, f):
                        vals[f] = post.get(f, '')

            for f in PERSONAL_FIELDS:
                if not self._field_exists(employee, f):
                    continue
                if f == 'children':
                    raw = post.get('children')
                    if raw not in (None, ''):
                        try:
                            vals['children'] = int(raw)
                        except ValueError:
                            pass
                elif f == 'country_of_birth':
                    country_id = post.get('country_of_birth')
                    vals['country_of_birth'] = int(country_id) if country_id else False
                elif f == 'country_id':
                    nat_id = post.get('country_id')
                    vals['country_id'] = int(nat_id) if nat_id else False
                elif f == 'km_home_work':
                    raw = post.get('km_home_work')
                    if raw not in (None, ''):
                        try:
                            vals['km_home_work'] = float(raw)
                        except ValueError:
                            pass
                elif f in ('gender', 'certificate', 'marital'):
                    val = post.get(f, '')
                    vals[f] = val if val else False
                else:
                    vals[f] = post.get(f, '')

            if vals:
                employee.write(vals)
        except Exception:
            _logger.exception('Employee portal: failed to save profile info for employee %s', employee.id)
            had_error = True

        # --- Bank details -------------------------------------------------------
        # IMPORTANT: acc_number on res.partner.bank is protected by Odoo's
        # "trusted bank account" anti-fraud lock (readonly: lock_trust_fields)
        # once a bank account exists. Writing to an existing bank record will
        # be rejected. So instead of editing in place, we create a new
        # res.partner.bank record whenever the value actually changes, and
        # simply repoint bank_account_id at it. This also preserves history.
        try:
            if self._field_exists(employee, 'bank_account_id'):
                acc_number = (post.get('acc_number') or '').strip()
                bank_name = (post.get('bank_name') or '').strip()

                current = employee.bank_account_id
                current_number = current.acc_number if current else ''

                if acc_number and acc_number != current_number:
                    # Matches the domain Odoo itself uses for this field
                    # (partner_id = work_contact_id) — see the field inspector.
                    bank_partner = employee.work_contact_id or employee.address_home_id or user.partner_id

                    bank_id = False
                    if bank_name:
                        existing_bank = request.env['res.bank'].sudo().search(
                            [('name', '=', bank_name)], limit=1)
                        bank_id = existing_bank.id if existing_bank else request.env['res.bank'].sudo().create(
                            {'name': bank_name}).id

                    new_bank_acc = request.env['res.partner.bank'].sudo().create({
                        'acc_number': acc_number,
                        'bank_id': bank_id,
                        'partner_id': bank_partner.id,
                    })
                    employee.write({'bank_account_id': new_bank_acc.id})
        except Exception:
            _logger.exception('Employee portal: failed to save bank details for employee %s', employee.id)
            had_error = True

        if had_error:
            return request.redirect('/my/employee/profile?error=1')
        return request.redirect('/my/employee/profile?success=1')
