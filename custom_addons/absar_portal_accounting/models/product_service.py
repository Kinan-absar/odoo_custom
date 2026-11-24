"""Company-scoped product forms for accounting; no generic portal product ACL."""
from odoo import models, _, Command
from odoo.exceptions import AccessError, UserError, ValidationError


class AccountingProducts(models.AbstractModel):
    _inherit = 'absar.portal.accounting.service'

    def _product_selection(self, product, company):
        account = product.product_tmpl_id.get_product_accounts().get('expense')
        return dict(id=product.id, name=product.display_name,
                    account_id=account.id if account else False,
                    account_name=account.display_name if account else '',
                    product_uom_id=product.uom_id.id, uom_name=product.uom_id.display_name,
                    tax_ids=[{'id': t.id, 'name': t.name} for t in product.supplier_taxes_id if t.company_id == company])

    def _accounting_product_version(self, product):
        return '%s|%s' % (product.write_date, product.product_tmpl_id.write_date)

    def _product_operation(self, company, kind, operation, data):
        user, roles = self._actor('preparer' if operation in ('product-create', 'product-update', 'product-defaults') else None)
        if kind not in ('bills', 'refunds') or not company.portal_accounting_journal_ids:
            raise AccessError(_('Products are available in the configured vendor bill workspace.'))
        Product = self._env(company)['product.product']
        product = Product.browse()
        if operation in ('product-read', 'product-update'):
            product = self._relation(company, 'product.product', data.get('id'),
                ['|', ('company_id', '=', False), ('company_id', '=', company.id), ('purchase_ok', '=', True)], True)
        pick = lambda r: {'id': r._origin.id, 'name': r.display_name} if r and r._origin.id else None
        if operation in ('product-read', 'product-defaults'):
            if not product:
                product = Product.new(dict(Product.default_get(['categ_id', 'uom_id', 'uom_po_id', 'supplier_taxes_id', 'purchase_method']),
                                           company_id=company.id, type='consu', purchase_ok=True))
            return dict(id=product._origin.id or False, name=product.name or '', type=product.type,
                can_edit=roles['preparer'], shared=not bool(product.company_id),
                version=self._accounting_product_version(product) if product._origin.id else '',
                categ_id=pick(product.categ_id), uom_id=pick(product.uom_id), uom_po_id=pick(product.uom_po_id),
                default_code=product.default_code or '', barcode=product.barcode or '', standard_price=product.standard_price,
                description_purchase=product.description_purchase or '', purchase_method=product.purchase_method or 'receive',
                is_storable=bool(product.is_storable), property_account_expense_id=pick(product.property_account_expense_id),
                category_expense_account=product.categ_id.property_account_expense_categ_id.display_name or '',
                supplier_taxes=[pick(t) for t in product.supplier_taxes_id if t.company_id == company and t._origin.id])
        if operation not in ('product-create', 'product-update'):
            raise AccessError(_('Unsupported product operation.'))
        if product:
            self.env.cr.execute('SELECT id FROM product_template WHERE id=%s FOR UPDATE', [product.product_tmpl_id.id])
            self.env.cr.execute('SELECT id FROM product_product WHERE id=%s FOR UPDATE', [product.id])
            product.invalidate_recordset()
            product.product_tmpl_id.invalidate_recordset()
            if not data.get('version') or data['version'] != self._accounting_product_version(product):
                raise UserError(_('This product changed. Close and reopen the product form.'))
        name = str(data.get('name') or '').strip()[:150]
        if not name or data.get('type') not in ('consu', 'service') or data.get('purchase_method') not in ('purchase', 'receive'):
            raise ValidationError(_('Enter a name, product type and bill control policy.'))
        category = self._relation(company, 'product.category', data.get('categ_id'), [], True)
        uom = self._relation(company, 'uom.uom', data.get('uom_id'), [('active', '=', True)], True)
        purchase_uom = self._relation(company, 'uom.uom', data.get('uom_po_id') or uom.id, [('active', '=', True)], True)
        if uom.category_id != purchase_uom.category_id:
            raise ValidationError(_('Purchase and product units must use the same category.'))
        account = self._account(company, data.get('property_account_expense_id'), required=False)
        taxes = self._m2m(company, 'account.tax', data.get('supplier_taxes_id', []),
            [('company_id', '=', company.id), ('type_tax_use', 'in', ['purchase', 'none'])])
        cost = self._number(data.get('standard_price'))
        if cost < 0:
            raise ValidationError(_('Cost cannot be negative.'))
        vals = dict(name=name, type=data['type'], is_storable=data['type'] == 'consu' and data.get('is_storable') is True,
            categ_id=category.id, uom_id=uom.id, uom_po_id=purchase_uom.id,
            property_account_expense_id=account.id or False, purchase_method=data['purchase_method'], standard_price=cost,
            default_code=str(data.get('default_code') or '')[:100], barcode=str(data.get('barcode') or '')[:100] or False,
            description_purchase=str(data.get('description_purchase') or '')[:4000])
        other_taxes = product.supplier_taxes_id.filtered(lambda t: t.company_id != company).ids if product else []
        vals['supplier_taxes_id'] = [Command.set(list(dict.fromkeys(taxes.ids + other_taxes)))]
        if product:
            product.write(vals)
        else:
            product = Product.create(dict(vals, company_id=company.id, purchase_ok=True, sale_ok=False))
        return dict(self._product_selection(product, company), product_updated=operation == 'product-update')
