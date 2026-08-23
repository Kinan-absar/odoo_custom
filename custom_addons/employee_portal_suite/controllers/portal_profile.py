from odoo import http
from odoo.http import request


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
BANK_FIELDS = [
    'acc_number',
    'bank_id',
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

        return request.render('employee_portal_suite.portal_employee_profile', {
            'employee': employee,
            'bank_account': bank_account,
            'has_bank_field': has_bank_field,
            'has_emergency_fields': self._field_exists(employee, 'emergency_contact'),
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

            if vals:
                employee.write(vals)

            # Bank details: update the linked res.partner.bank record if the
            # employee model supports it, creating one on first save.
            if self._field_exists(employee, 'bank_account_id'):
                acc_number = (post.get('acc_number') or '').strip()
                bank_name = (post.get('bank_name') or '').strip()

                if acc_number:
                    bank_partner = employee.address_home_id or employee.work_contact_id or user.partner_id
                    bank_id = False
                    if bank_name:
                        existing_bank = request.env['res.bank'].sudo().search(
                            [('name', '=', bank_name)], limit=1)
                        bank_id = existing_bank.id if existing_bank else request.env['res.bank'].sudo().create(
                            {'name': bank_name}).id

                    if employee.bank_account_id:
                        employee.bank_account_id.sudo().write({
                            'acc_number': acc_number,
                            'bank_id': bank_id,
                        })
                    else:
                        new_bank_acc = request.env['res.partner.bank'].sudo().create({
                            'acc_number': acc_number,
                            'bank_id': bank_id,
                            'partner_id': bank_partner.id,
                        })
                        employee.write({'bank_account_id': new_bank_acc.id})

            return request.redirect('/my/employee/profile?success=1')
        except Exception:
            return request.redirect('/my/employee/profile?error=1')
