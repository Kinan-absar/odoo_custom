"""Native purchase ORM access without impersonating an internal user.

The native webclient uses the normal authenticated ORM. ACLs/rules therefore
apply to every request, including direct JSON-RPC, and are not just UI filters.
"""
import math
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

PREFIX = 'absar_portal_purchase_monitor.'
NATIVE = PREFIX + 'group_portal_purchase_native'


def native_portal(env):
    return bool(env.user.share and env.user.has_group(NATIVE))


def guard_actor(env, role=None):
    user = env.user.sudo(False)
    if not native_portal(env) or not user.active or not user.employee_id or user.has_group('employee_portal_suite.group_attendance_only'):
        raise AccessError(_('Native purchase workspace access is required.'))
    if role and not user.has_group(PREFIX + 'group_portal_purchase_' + role):
        raise AccessError(_('You do not have this purchase permission.'))
    return user


def company_record(env, company_id):
    company = env['res.company'].browse(int(company_id or env.company.id)).exists()
    if not company or company not in env.user.company_ids:
        raise AccessError(_('Company is not available.'))
    return company


def check_relation(env, name, ident, company):
    if not ident:
        return
    record = env[name].browse(int(ident)).exists()
    record.check_access('read')
    if not record:
        raise ValidationError(_('Selected record no longer exists.'))
    if 'company_ids' in record._fields and name == 'account.account':
        if company not in record.company_ids:
            raise ValidationError(_('Account belongs to another company.'))
    elif 'company_id' in record._fields and record.company_id and record.company_id != company:
        raise ValidationError(_('Selection belongs to another company.'))


def check_fields(record, vals, allowed):
    """Custom editable scalar fields are retained; arbitrary relations are not."""
    for name in vals:
        if name in allowed:
            continue
        field = record._fields.get(name)
        safe_custom = (name.startswith('x_') and field and not field.related and
                       not field.compute and not field.readonly and field.type in (
                           'char', 'text', 'html', 'boolean', 'integer', 'float',
                           'monetary', 'date', 'datetime', 'selection'))
        safe_relation = (name.startswith('x_') and field and not field.related and
                         not field.compute and not field.readonly and field.type == 'many2one' and
                         field.comodel_name in {'account.account', 'account.analytic.account',
                            'project.project', 'res.partner', 'product.product', 'uom.uom'})
        if safe_relation:
            check_relation(record.env, field.comodel_name, vals[name], record.env.company)
        if not (safe_custom or safe_relation):
            raise AccessError(_('Field %s is not writable through the purchase workspace.') % name)


class ResUsers(models.Model):
    _inherit = 'res.users'

    absar_purchase_project_ids = fields.Many2many(
        'project.project', compute='_compute_absar_purchase_projects',
        string='Purchase Workspace Assigned Projects', compute_sudo=True)

    def _compute_absar_purchase_projects(self):
        for user in self:
            employees = self.env['hr.employee'].sudo().search([
                ('user_id', '=', user.id), ('company_id', 'in', user.company_ids.ids)])
            projects = self.env['project.project'].sudo().browse()
            for employee in employees:
                projects |= employee._get_material_request_projects()
            user.absar_purchase_project_ids = projects.filtered(
                lambda p: p.active and (not p.company_id or p.company_id in user.company_ids))

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if native_portal(self.env):
            guard_actor(self.env)
            domain = [('active', '=', True), ('share', '=', False),
                      ('company_ids', 'in', self.env.user.company_ids.ids)] + list(args or [])
            for term in args or []:
                if isinstance(term, (list, tuple)) and term[0] not in {'id', 'name', 'active', 'share', 'company_id', 'company_ids'}:
                    raise AccessError(_('Unsupported buyer search filter.'))
            # Names/IDs only: do not grant portal users broad res.users read ACLs.
            return super(ResUsers, self.sudo()).name_search(name, domain, operator, min(limit or 100, 100))
        return super().name_search(name, args, operator, limit)

    @api.readonly
    def web_read(self, specification):
        safe_fields = {'id', 'display_name', 'avatar_128', 'avatar_256', 'im_status', 'share'}
        if native_portal(self.env) and set(specification) <= safe_fields:
            guard_actor(self.env)
            allowed = self.sudo().filtered(lambda u:
                u == self.env.user or (u.active and not u.share and bool(u.company_ids & self.env.user.company_ids)))
            if set(allowed.ids) != set(self.ids):
                raise AccessError(_('Buyer is not available.'))
            return super(ResUsers, allowed).web_read(specification)
        return super().web_read(specification)


ORDER_FIELDS = {
    'partner_id', 'partner_ref', 'user_id', 'company_id', 'currency_id', 'date_order',
    'date_planned', 'project_id', 'material_request_id', 'origin', 'notes', 'priority',
    'order_line', 'payment_term_id', 'fiscal_position_id', 'incoterm_id',
    'incoterm_location', 'picking_type_id', 'dest_address_id', 'receipt_reminder_email',
    'reminder_date_before_receipt', 'quotation_attachment_ids', 'absar_expense_account_id',
}
LINE_FIELDS = {
    'order_id', 'sequence', 'display_type', 'product_id', 'name', 'product_qty',
    'product_uom', 'price_unit', 'discount', 'taxes_id', 'date_planned',
    'analytic_distribution', 'absar_expense_account_id', 'product_packaging_id',
    'product_packaging_qty', 'propagate_cancel', 'product_no_variant_attribute_value_ids',
}


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _native_validate_values(self, vals, create=False):
        user = guard_actor(self.env, 'preparer')
        check_fields(self, vals, ORDER_FIELDS)
        company = company_record(self.env, vals.get('company_id') or (self.company_id.id if self else False))
        if self and vals.get('company_id') and self.company_id != company:
            raise ValidationError(_('An existing RFQ cannot be moved to another company.'))
        fields_map = {'partner_id': 'res.partner', 'currency_id': 'res.currency',
                      'project_id': 'project.project', 'material_request_id': 'material.request',
                      'user_id': 'res.users', 'payment_term_id': 'account.payment.term',
                      'fiscal_position_id': 'account.fiscal.position', 'incoterm_id': 'account.incoterms',
                      'picking_type_id': 'stock.picking.type', 'dest_address_id': 'res.partner'}
        for name, model in fields_map.items():
            if name in vals and vals[name]:
                if model == 'res.users':
                    buyer = self.env[model].sudo().browse(int(vals[name])).exists()
                    if not buyer or buyer.share or company not in buyer.company_ids:
                        raise ValidationError(_('Choose an internal buyer in the order company.'))
                else:
                    check_relation(self.env, model, vals[name], company)
        project = self.env['project.project'].browse(vals.get('project_id') or (self.project_id.id if self else False))
        if project and project not in user.absar_purchase_project_ids:
            raise AccessError(_('This project is not assigned to your work locations.'))
        mr_id = vals.get('material_request_id', self.material_request_id.id if self else False)
        if mr_id:
            mr = self.env['material.request'].browse(mr_id)
            mr.check_access('read')
            if (mr.project_id.company_id or mr.employee_id.company_id) != company:
                raise ValidationError(_('Material Request belongs to another company.'))
            if mr.state != 'approved' or mr.no_po_required:
                raise ValidationError(_('Choose an approved Material Request requiring a PO.'))
            if mr.project_id and project != mr.project_id:
                raise ValidationError(_('Project must match the linked Material Request.'))
        if 'order_line' in vals:
            for command in vals['order_line']:
                if not isinstance(command, (list, tuple)) or not command:
                    raise AccessError(_('Invalid line operation.'))
                if command[0] not in (0, 1, 2, 5):
                    raise AccessError(_('Moving or linking existing lines is not allowed.'))
                if command[0] in (1, 2):
                    if not self or command[1] not in self.order_line.ids:
                        raise AccessError(_('This line does not belong to this RFQ.'))
        if 'quotation_attachment_ids' in vals:
            for command in vals['quotation_attachment_ids']:
                if command[0] not in (3, 4, 6):
                    raise AccessError(_('Select an existing attachment belonging to this RFQ.'))
                ids = command[2] if command[0] == 6 else [command[1]]
                attachments = self.env['ir.attachment'].browse(ids)
                attachments.check_access('read')
                if any(a.res_model != 'purchase.order' or not self or a.res_id != self.id for a in attachments):
                    raise AccessError(_('Quotation attachment must belong to this RFQ.'))
        return company

    @api.model_create_multi
    def create(self, vals_list):
        if native_portal(self.env) and not self.env.su:
            user = guard_actor(self.env, 'preparer')
            for vals in vals_list:
                # Native readonly/default values can be sent by web_save; never trust them.
                vals.pop('name', None)
                if vals.pop('state', 'draft') != 'draft':
                    raise AccessError(_('Only draft RFQs can be created.'))
                vals.pop('absar_portal_review_state', None)
                vals.pop('absar_portal_preparer_id', None)
                self._native_validate_values(vals, create=True)
                vals.update(absar_portal_preparer_id=user.id, absar_portal_review_state='draft')
        return super().create(vals_list)

    def write(self, vals):
        if native_portal(self.env) and not self.env.su:
            for po in self:
                po._portal_lock()
                if not po._portal_editable(self.env.user):
                    raise AccessError(_('Only your own eligible draft RFQ can be edited.'))
                po._native_validate_values(vals)
        return super().write(vals)

    @api.onchange('material_request_id')
    def _onchange_native_purchase_mr(self):
        if native_portal(self.env) and self.material_request_id:
            self.material_request_id.check_access('read')
            self.project_id = self.material_request_id.project_id

    def action_absar_portal_submit(self):
        for po in self:
            po.check_access('read')
            po._portal_submit()
        return True

    def button_confirm(self):
        if native_portal(self.env) and not self.env.su:
            return self.action_absar_portal_confirm()
        return super().button_confirm()

    def button_approve(self, force=False):
        if native_portal(self.env) and not self.env.su:
            raise AccessError(_('Native manager approval must be completed by an authorized internal purchase manager.'))
        return super().button_approve(force=force)

    def button_cancel(self):
        if native_portal(self.env) and not self.env.su:
            for po in self:
                if not po._portal_editable(self.env.user):
                    raise AccessError(_('Only your own unsubmitted draft RFQ can be cancelled here.'))
            # The narrow native method is allowed after ownership/state checks.
            return super(PurchaseOrder, self.sudo()).button_cancel()
        return super().button_cancel()

    def button_draft(self):
        if native_portal(self.env) and not self.env.su:
            guard_actor(self.env, 'preparer')
            for po in self:
                po.check_access('read')
                if po.absar_portal_preparer_id != self.env.user or po.state != 'cancel':
                    raise AccessError(_('Only your own cancelled RFQ can be reset.'))
            return super(PurchaseOrder, self.sudo()).button_draft()
        return super().button_draft()

    def button_done(self):
        if native_portal(self.env) and not self.env.su:
            raise AccessError(_('Purchase locking requires the internal purchasing workflow.'))
        return super().button_done()

    def button_unlock(self):
        if native_portal(self.env) and not self.env.su:
            raise AccessError(_('Purchase unlocking requires an internal purchase manager.'))
        return super().button_unlock()

    def action_create_invoice(self):
        if native_portal(self.env) and not self.env.su:
            raise AccessError(_('Vendor bill creation requires an authorized internal accountant.'))
        return super().action_create_invoice()


class PurchaseLine(models.Model):
    _inherit = 'purchase.order.line'

    def _native_validate_line(self, vals, order):
        guard_actor(self.env, 'preparer')
        order.check_access('read')
        if not order._portal_editable(self.env.user):
            raise AccessError(_('RFQ is not an editable draft belonging to you.'))
        check_fields(self, vals, LINE_FIELDS)
        for name, model in [('product_id', 'product.product'), ('product_uom', 'uom.uom'),
                            ('absar_expense_account_id', 'account.account')]:
            if vals.get(name):
                check_relation(self.env, model, vals[name], order.company_id)
        for name in ('product_qty', 'price_unit', 'discount'):
            if name in vals and not math.isfinite(float(vals[name])):
                raise ValidationError(_('Quantity, price and discount must be finite numbers.'))
        display = vals.get('display_type', self.display_type if self else False)
        if not display and vals.get('product_qty', self.product_qty if self else 1) <= 0:
            raise ValidationError(_('Quantity must be greater than zero.'))
        if 'analytic_distribution' in vals:
            distribution = vals['analytic_distribution'] or {}
            if not isinstance(distribution, dict) or len(distribution) > 100:
                raise ValidationError(_('Invalid analytic distribution.'))
            seen_combinations = set()
            for key, percentage in distribution.items():
                if not math.isfinite(float(percentage)) or not 0 <= float(percentage) <= 100:
                    raise ValidationError(_('Invalid analytic percentage.'))
                try:
                    ids = [int(v) for v in key.split(',')]
                except (ValueError, AttributeError):
                    raise ValidationError(_('Invalid analytic account.'))
                if len(ids) > 20 or len(ids) != len(set(ids)) or any(v <= 0 for v in ids):
                    raise ValidationError(_('Invalid analytic account combination.'))
                canonical = tuple(sorted(ids))
                if canonical in seen_combinations:
                    raise ValidationError(_('Duplicate analytic account combination.'))
                seen_combinations.add(canonical)
                plans = set()
                for ident in ids:
                    check_relation(self.env, 'account.analytic.account', ident, order.company_id)
                    account = self.env['account.analytic.account'].browse(ident)
                    plan = account.root_plan_id.id
                    if plan in plans:
                        raise ValidationError(_('Choose only one account from each plan per distribution row.'))
                    plans.add(plan)
            # Native mandatory-plan totals remain checked by Odoo at submission/confirmation.
        if 'product_no_variant_attribute_value_ids' in vals:
            product = self.env['product.product'].browse(vals.get('product_id') or (self.product_id.id if self else False))
            for command in vals['product_no_variant_attribute_value_ids']:
                if command[0] not in (3, 4, 5, 6):
                    raise AccessError(_('Select existing product attribute values.'))
                ids = command[2] if command[0] == 6 else [] if command[0] == 5 else [command[1]]
                for value in self.env['product.template.attribute.value'].browse(ids):
                    value.check_access('read')
                    if value.product_tmpl_id != product.product_tmpl_id:
                        raise ValidationError(_('Attribute value must belong to the selected product.'))
        for command in vals.get('taxes_id', []):
            if command[0] not in (3, 4, 5, 6):
                raise AccessError(_('Creating or changing tax definitions is not allowed.'))
            ids = command[2] if command[0] == 6 else [] if command[0] == 5 else [command[1]]
            for ident in ids:
                tax = self.env['account.tax'].browse(ident)
                check_relation(self.env, 'account.tax', ident, order.company_id)
                if tax.type_tax_use != 'purchase':
                    raise ValidationError(_('Choose a purchase tax.'))

    @api.model_create_multi
    def create(self, vals_list):
        if native_portal(self.env) and not self.env.su:
            for vals in vals_list:
                order = self.env['purchase.order'].browse(int(vals.get('order_id') or 0))
                self._native_validate_line(vals, order)
        return super().create(vals_list)

    def write(self, vals):
        if native_portal(self.env) and not self.env.su:
            if 'order_id' in vals:
                raise AccessError(_('Moving a line between RFQs is not allowed.'))
            for line in self:
                line._native_validate_line(vals, line.order_id)
        return super().write(vals)

    def unlink(self):
        if native_portal(self.env) and not self.env.su:
            for line in self:
                line._native_validate_line({}, line.order_id)
        return super().unlink()
