from copy import deepcopy
from odoo import api, models, _
from odoo.exceptions import AccessError, ValidationError
from .native_access import native_portal, guard_actor, check_relation, check_fields, company_record

PRODUCT_FIELDS = {
    'name', 'default_code', 'barcode', 'type', 'is_storable', 'purchase_ok', 'sale_ok',
    'company_id', 'categ_id', 'uom_id', 'uom_po_id', 'list_price', 'standard_price',
    'supplier_taxes_id', 'taxes_id', 'purchase_method', 'invoice_policy',
    'description', 'description_purchase', 'description_sale', 'description_picking',
    'description_pickingin', 'description_pickingout', 'image_1920', 'image_1024',
    'weight', 'volume', 'sale_delay', 'seller_ids', 'variant_seller_ids',
    'property_account_expense_id', 'property_account_income_id',
    'expense_policy', 'can_be_expensed', 'available_in_pos', 'sequence',
    'responsible_id', 'tracking', 'service_tracking', 'service_type', 'color', 'purchase_requisition', 'purchase_line_warn', 'purchase_line_warn_msg',
    'sale_line_warn', 'sale_line_warn_msg', 'priority', 'product_tag_ids',
    'route_ids', 'attribute_line_ids', 'product_template_variant_value_ids',
    'product_template_attribute_value_ids', 'combination_indices', 'product_tmpl_id', 'active',
}


def validate_product(model, vals, existing=False):
    user = guard_actor(model.env, 'product_creator')
    if not user.has_group('absar_portal_purchase_monitor.group_portal_purchase_preparer'):
        raise AccessError(_('Purchase preparation permission is required.'))
    check_fields(model, vals, PRODUCT_FIELDS)
    company = company_record(model.env, vals.get('company_id') or (existing.company_id.id if existing else False))
    if existing:
        existing.check_access('read')
        if existing.create_uid != user or existing.company_id != company:
            raise AccessError(_('Only products you created in this company can be changed.'))
    if 'purchase_ok' in vals and not vals['purchase_ok']:
        raise ValidationError(_('A product created here must remain purchasable.'))
    for name, related in [('categ_id', 'product.category'), ('uom_id', 'uom.uom'), ('uom_po_id', 'uom.uom'),
                          ('property_account_expense_id', 'account.account'), ('property_account_income_id', 'account.account')]:
        if vals.get(name):
            check_relation(model.env, related, vals[name], company)
    for name in ('supplier_taxes_id', 'taxes_id'):
        for command in vals.get(name, []):
            if command[0] not in (3, 4, 5, 6):
                raise AccessError(_('Tax definitions cannot be created or edited here.'))
            ids = command[2] if command[0] == 6 else [] if command[0] == 5 else [command[1]]
            for ident in ids:
                check_relation(model.env, 'account.tax', ident, company)
    # Nested supplier/attribute commands are secured by their own ACLs/rules;
    # direct template switching would otherwise be able to attach another product.
    if existing and 'product_tmpl_id' in vals and vals['product_tmpl_id'] != existing.product_tmpl_id.id:
        raise AccessError(_('Moving a variant to a different template is not allowed.'))
    return company


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if native_portal(self.env) and not self.env.user.has_group('absar_portal_purchase_monitor.group_portal_purchase_product_creator'):
            arch = deepcopy(arch)
            arch.set('create', 'false')
            arch.set('edit', 'false')
            arch.set('delete', 'false')
        return arch, view

    @api.model_create_multi
    def create(self, vals_list):
        if native_portal(self.env) and not self.env.su:
            for vals in vals_list:
                company = validate_product(self, vals)
                vals.update(company_id=company.id, purchase_ok=True)
        return super().create(vals_list)

    def write(self, vals):
        if native_portal(self.env) and not self.env.su:
            for product in self:
                validate_product(self, vals, product)
        return super().write(vals)

    def unlink(self):
        if native_portal(self.env) and not self.env.su:
            raise AccessError(_('Product deletion is not available in the purchase workspace.'))
        return super().unlink()


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if native_portal(self.env) and not self.env.user.has_group('absar_portal_purchase_monitor.group_portal_purchase_product_creator'):
            arch = deepcopy(arch)
            arch.set('create', 'false')
            arch.set('edit', 'false')
            arch.set('delete', 'false')
        return arch, view

    @api.model_create_multi
    def create(self, vals_list):
        if native_portal(self.env) and not self.env.su:
            for vals in vals_list:
                company = validate_product(self, vals)
                if vals.get('product_tmpl_id'):
                    template = self.env['product.template'].browse(vals['product_tmpl_id'])
                    if template.create_uid != self.env.user or template.company_id != company:
                        raise AccessError(_('Variants can only be added to a product you created.'))
                else:
                    vals.update(company_id=company.id, purchase_ok=True)
        return super().create(vals_list)

    def write(self, vals):
        if native_portal(self.env) and not self.env.su:
            for product in self:
                validate_product(self, vals, product)
        return super().write(vals)

    def unlink(self):
        if native_portal(self.env) and not self.env.su:
            raise AccessError(_('Product deletion is not available here.'))
        return super().unlink()


class SupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    def _check_native_supplier(self, vals, record=False):
        guard_actor(self.env, 'product_creator')
        tmpl_id = vals.get('product_tmpl_id') or (record.product_tmpl_id.id if record else False)
        product_id = vals.get('product_id') or (record.product_id.id if record else False)
        template = self.env['product.template'].browse(tmpl_id)
        if not template and product_id:
            template = self.env['product.product'].browse(product_id).product_tmpl_id
        template.check_access('read')
        if not template or template.create_uid != self.env.user:
            raise AccessError(_('Vendor prices can only be changed for products you created.'))
        company = template.company_id
        if not company or company not in self.env.user.company_ids:
            raise AccessError(_('Product company is not available.'))
        if product_id:
            product = self.env['product.product'].browse(product_id)
            product.check_access('read')
            if product.product_tmpl_id != template:
                raise AccessError(_('Vendor price variant must belong to its product template.'))
        check_fields(self, vals, {'partner_id', 'product_id', 'product_tmpl_id', 'product_name',
            'product_code', 'sequence', 'min_qty', 'price', 'currency_id', 'date_start',
            'date_end', 'delay', 'company_id', 'discount'})
        if vals.get('partner_id'):
            check_relation(self.env, 'res.partner', vals['partner_id'], company)
        if vals.get('company_id') and vals['company_id'] != company.id:
            raise AccessError(_('Vendor price company must match the product.'))

    @api.model_create_multi
    def create(self, vals_list):
        if native_portal(self.env) and not self.env.su:
            for vals in vals_list:
                self._check_native_supplier(vals)
        return super().create(vals_list)

    def write(self, vals):
        if native_portal(self.env) and not self.env.su:
            for record in self:
                record._check_native_supplier(vals, record)
        return super().write(vals)

    def unlink(self):
        if native_portal(self.env) and not self.env.su:
            for record in self:
                record._check_native_supplier({}, record)
        return super().unlink()
