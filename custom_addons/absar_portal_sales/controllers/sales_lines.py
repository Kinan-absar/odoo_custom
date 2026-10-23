"""Scoped native-style sales lines; portal users receive no generic model ACL."""
import json
from odoo import Command, fields, _
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression
from werkzeug.exceptions import Forbidden, NotFound


class SalesLinesMixin:
    def _line_new_order(self, data, required=False):
        user=self._allowed()
        header=data.get('header') or {}
        if not isinstance(header,dict):raise ValidationError(_('Invalid quotation details.'))
        partner=False
        if header.get('partner_id'):
            partner=request.env['res.partner'].sudo().browse(self._line_id(header['partner_id'])).exists()
            if not partner or partner not in self._partners(limit=None) or (partner.company_id and partner.company_id!=user.company_id):
                raise ValidationError(_('Select an available customer for this company.'))
        if required and not partner:raise ValidationError(_('Select a customer.'))
        if required and not header.get('date_order'):raise ValidationError(_('Set the quotation/order date.'))
        project=False
        if header.get('project_id'):
            project=request.env['project.project'].sudo().browse(self._line_id(header['project_id'])).exists()
            if not partner or not project or project not in self._customer_projects(partner) or (project.company_id and project.company_id!=user.company_id):
                raise ValidationError(_('Select a project assigned to this customer and company.'))
        kind=header.get('kind') or 'standard'
        if kind not in ('standard','technical'):raise ValidationError(_('Invalid quotation type.'))
        vals=dict(partner_id=partner.id if partner else False,company_id=user.company_id.id,user_id=user.id,
            absar_portal_creator_id=user.id,absar_proposal_type=kind,construction_project_id=project.id if project else False,
            date_order=self._sales_date_utc(header['date_order']) if header.get('date_order') else fields.Datetime.now(),
            validity_date=fields.Date.to_date(header['validity_date']) if header.get('validity_date') else False)
        return request.env['sale.order'].sudo().with_company(user.company_id).new(vals),vals

    def _line_header_values(self, order, header):
        if not isinstance(header,dict):raise ValidationError(_('Invalid quotation details.'))
        project=False
        if header.get('project_id'):
            project=request.env['project.project'].sudo().browse(self._line_id(header['project_id'])).exists()
            if not project or project not in self._customer_projects(order.partner_id) or (project.company_id and project.company_id!=order.company_id):
                raise ValidationError(_('Select an available project for this customer and company.'))
        vals=dict(construction_project_id=project.id if project else False,
            date_order=self._sales_date_utc(header.get('date_order')),
            validity_date=fields.Date.to_date(header['validity_date']) if header.get('validity_date') else False)
        if order.absar_proposal_type=='technical':vals['absar_proposal_title']=str(header.get('title') or 'Technical & Financial Proposal')[:160]
        return vals

    def _line_pricing_values(self, order, data):
        vals=dict(partner_id=order.partner_id.id,company_id=order.company_id.id,
            pricelist_id=order.pricelist_id.id,currency_id=order.currency_id.id,
            fiscal_position_id=order.fiscal_position_id.id,date_order=order.date_order)
        if order.id and 'header' in data:
            vals.update(self._line_header_values(order,data['header']))
        return vals

    def _line_env(self, order):
        return request.env(context=dict(request.env.context, allowed_company_ids=[order.company_id.id]))['sale.order'].with_company(order.company_id).sudo().env

    def _line_id(self, value):
        if isinstance(value, bool):
            raise ValidationError(_('Invalid identifier.'))
        try:
            rid = int(value)
            if rid <= 0 or str(rid) != str(value):
                raise ValueError()
            return rid
        except (ValueError, TypeError, OverflowError):
            raise ValidationError(_('Invalid identifier.'))

    def _line_scope(self, order, kind):
        company = order.company_id
        scopes = {
            'product': ('product.product', [('active','=',True),('sale_ok','=',True),'|',('company_id','=',False),('company_id','=',company.id)]),
            'category': ('product.category', []),
            'income-account': ('account.account', [('company_ids','in',company.id),('deprecated','=',False),('account_type','in',['income','income_other'])]),
            'uom': ('uom.uom', [('active','=',True)]),
            'tax': ('account.tax', [('active','=',True),('company_id','=',company.id),('type_tax_use','in',['sale','none'])]),
            'analytic': ('account.analytic.account', [('active','=',True),'|',('company_id','=',False),('company_id','=',company.id)]),
        }
        if kind not in scopes:
            raise AccessError(_('Unsupported selection.'))
        return scopes[kind]

    def _line_choice(self, order, kind, value):
        model, domain = self._line_scope(order, kind)
        record = self._line_env(order)[model].search(expression.AND([domain,[('id','=',self._line_id(value))]]),limit=1)
        if not record:
            raise AccessError(_('Selected record is unavailable for this quotation company.'))
        return record

    def _line_version(self, order):
        return json.dumps([str(order.write_date),[(l.id,str(l.write_date)) for l in order.order_line.sorted('id')]],separators=(',',':'))

    def _line_analytic(self, order, raw):
        if not isinstance(raw,dict) or len(raw)>100:
            raise ValidationError(_('Invalid analytic distribution.'))
        result, totals = {}, {}
        for key, percent in raw.items():
            ids = [self._line_id(v) for v in str(key).split(',')]
            if len(ids)>20 or len(set(ids))!=len(ids):
                raise ValidationError(_('Invalid analytic combination.'))
            accounts=[self._line_choice(order,'analytic',rid) for rid in ids]
            plans=[a.plan_id.root_id.id for a in accounts]
            if len(set(plans))!=len(plans):
                raise ValidationError(_('Use one analytic account per plan in each row.'))
            pct=self._num(percent,'Percentage')
            if not 0<pct<=100:
                raise ValidationError(_('Every allocation percentage must be greater than zero and at most 100.'))
            canonical=','.join(str(rid) for rid in sorted(ids))
            if canonical in result:
                raise ValidationError(_('Combine duplicate allocation rows.'))
            result[canonical]=pct
            for plan in plans:
                totals[plan]=totals.get(plan,0)+pct
        if any(abs(total-100)>.01 for total in totals.values()):
            raise ValidationError(_('Each used analytic plan must total 100%.'))
        return result

    def _line_data(self, line):
        pick=lambda r: {'id':r._origin.id,'label':r.display_name} if r and r._origin.id else None
        return dict(id=line.id if isinstance(line.id,int) and line.id>0 else 0,
            product_id=line.product_id._origin.id or 0,product=pick(line.product_id),name=line.name or '',
            quantity=line.product_uom_qty,uom_id=line.product_uom._origin.id or 0,uom=pick(line.product_uom),
            price_unit=line.price_unit,discount=line.discount,taxes_id=line.tax_id.ids,taxes=[pick(t) for t in line.tax_id if t._origin.id],
            analytic_distribution=line.analytic_distribution or {},display_type=line.display_type or '',subtotal=line.price_subtotal)

    def _line_boot(self, order):
        editable=True
        try:self._editable(order)
        except Forbidden:editable=False
        ids={int(part) for line in order.order_line for key in (line.analytic_distribution or {}) for part in str(key).split(',') if part.isdigit()}
        model,domain=self._line_scope(order,'analytic')
        accounts=self._line_env(order)[model].search(expression.AND([domain,[('id','in',sorted(ids))]]))
        labels={str(a.id):dict(id=a.id,label=a.display_name,plan=a.plan_id.root_id.display_name,plan_id=a.plan_id.root_id.id) for a in accounts}
        return dict(order_id=order.id or 0,company_id=order.company_id.id,editable=editable,version=self._line_version(order) if order.id else '',
            lines=[self._line_data(l) for l in order.order_line.sorted(lambda l:(l.sequence,l.id))],analytic_labels=labels,
            currency=order.currency_id.name,untaxed=order.amount_untaxed,tax=order.amount_tax,total=order.amount_total)

    def _line_values(self, order, row):
        if not isinstance(row,dict):
            raise ValidationError(_('Invalid line.'))
        name=str(row.get('name') or '').strip()[:8000]
        if not name:
            raise ValidationError(_('Enter a product or description on every line.'))
        display=row.get('display_type') or False
        if display:
            if display not in ('line_section','line_note'):
                raise ValidationError(_('Invalid line type.'))
            return dict(display_type=display,name=name)
        product=self._line_choice(order,'product',row['product_id']) if row.get('product_id') else False
        if not product and not row.get('id'):
            raise ValidationError(_('Choose a product on each new line.'))
        uom=self._line_choice(order,'uom',row.get('uom_id'))
        if product and product.uom_id.category_id!=uom.category_id:
            raise ValidationError(_('Product and unit must have the same unit category.'))
        quantity=self._num(row.get('quantity'),'Quantity');price=self._num(row.get('price_unit'),'Unit Price');discount=self._num(row.get('discount'),'Discount')
        if quantity<=0 or discount>100:
            raise ValidationError(_('Quantity must be positive and discount must be between 0 and 100.'))
        taxes=row.get('taxes_id',[])
        if not isinstance(taxes,list) or len(taxes)>50:
            raise ValidationError(_('Invalid taxes.'))
        tax_ids=list(dict.fromkeys(self._line_choice(order,'tax',rid).id for rid in taxes))
        return dict(product_id=product.id if product else False,name=name,product_uom=uom.id,product_uom_qty=quantity,
            price_unit=price,discount=discount,tax_id=[Command.set(tax_ids)],analytic_distribution=self._line_analytic(order,row.get('analytic_distribution') or {}))

    def _line_product(self, order, operation, data):
        self._editable(order)
        Product=self._line_env(order)['product.product']
        product=self._line_choice(order,'product',data['id']) if data.get('id') else False
        if operation in ('product-read','product-defaults'):
            if operation=='product-read' and not product:raise ValidationError(_('Choose a product.'))
            defaults=Product.default_get(['categ_id','uom_id','taxes_id']) if not product else {}
            if not product and order.company_id.account_sale_tax_id:
                defaults['taxes_id']=[Command.set(order.company_id.account_sale_tax_id.ids)]
            p=product or Product.new(dict(defaults,type='consu',company_id=order.company_id.id))
            pick=lambda r: {'id':r._origin.id,'label':r.display_name} if r and r._origin.id else None
            return dict(id=product.id if product else 0,name=p.name or '',type=p.type,
                version=('%s|%s'%(p.write_date,p.product_tmpl_id.write_date)) if product else '',
                shared=bool(product and not product.company_id),categ_id=pick(p.categ_id),uom_id=pick(p.uom_id),
                list_price=p.list_price,default_code=p.default_code or '',description_sale=p.description_sale or '',
                income_account=pick(p.property_account_income_id),taxes=[pick(t) for t in p.taxes_id if t.company_id==order.company_id and t._origin.id])
        if operation not in ('product-create','product-update'):raise AccessError(_('Unsupported product operation.'))
        if operation=='product-update' and not product:raise ValidationError(_('Choose a product.'))
        if product:
            request.env.cr.execute('SELECT id FROM product_template WHERE id=%s FOR UPDATE',[product.product_tmpl_id.id])
            request.env.cr.execute('SELECT id FROM product_product WHERE id=%s FOR UPDATE',[product.id])
            product.invalidate_recordset();product.product_tmpl_id.invalidate_recordset()
            if not data.get('version') or data['version']!='%s|%s'%(product.write_date,product.product_tmpl_id.write_date):
                raise UserError(_('This product changed. Reopen its form.'))
        name=str(data.get('name') or '').strip()[:150]
        if not name or data.get('type') not in ('consu','service'):raise ValidationError(_('Enter a name and product type.'))
        category=self._line_choice(order,'category',data.get('categ_id'));unit=self._line_choice(order,'uom',data.get('uom_id'))
        account=self._line_choice(order,'income-account',data['income_account_id']) if data.get('income_account_id') else False
        taxes=data.get('taxes_id',[])
        if not isinstance(taxes,list) or len(taxes)>50:raise ValidationError(_('Invalid sales taxes.'))
        ids=list(dict.fromkeys(self._line_choice(order,'tax',rid).id for rid in taxes))
        if product:ids+=product.taxes_id.filtered(lambda t:t.company_id!=order.company_id).ids
        vals=dict(name=name,type=data['type'],categ_id=category.id,uom_id=unit.id,list_price=self._num(data.get('list_price'),'Sales Price'),
                  default_code=str(data.get('default_code') or '')[:100],description_sale=str(data.get('description_sale') or '')[:4000],
                  property_account_income_id=account.id if account else False,taxes_id=[Command.set(ids)])
        if product:product.write(vals)
        else:product=Product.create(dict(vals,company_id=order.company_id.id,sale_ok=True,purchase_ok=False,uom_po_id=unit.id))
        return dict(id=product.id,label=product.display_name,product_updated=operation=='product-update')

    def _line_api(self, order_id, operation, post):
        try:
            if request.httprequest.content_length and request.httprequest.content_length>2_000_000:
                raise ValidationError(_('Request is too large.'))
            data=json.loads(post.get('payload') or '{}')
            if not isinstance(data,dict):raise ValidationError(_('Invalid request.'))
            with request.env.cr.savepoint():
                order=self._order(order_id) if order_id else self._line_new_order(data)[0]
                if not order_id and operation not in ('lookup','defaults','preview','create','product-read','product-defaults','product-create','product-update'):
                    raise AccessError(_('Unsupported new quotation operation.'))
                if operation in ('product-read','product-defaults','product-create','product-update'):
                    result=self._line_product(order,operation,data)
                elif operation=='lookup':
                    kind=data.get('kind')
                    if kind in ('income-account','category'):self._editable(order)
                    model,domain=self._line_scope(order,kind)
                    query=str(data.get('q') or '')[:120]
                    if query:
                        fields=['name','default_code','barcode'] if kind=='product' else ['name']
                        domain=expression.AND([domain,expression.OR([[(f,'ilike',query)] for f in fields])])
                    offset=max(0,min(int(data.get('offset') or 0),100000))
                    rows=self._line_env(order)[model].search(domain,order='id',limit=31,offset=offset)
                    result={'items':[dict(id=r.id,label=r.display_name,**({'plan':r.plan_id.root_id.display_name,'plan_id':r.plan_id.root_id.id} if kind=='analytic' else {})) for r in rows[:30]],'more':len(rows)>30}
                elif operation=='defaults':
                    self._editable(order)
                    product=self._line_choice(order,'product',data.get('product_id'))
                    qty=self._num(data.get('quantity') or 1,'Quantity')
                    if not order.partner_id:raise ValidationError(_('Select a customer before choosing products.'))
                    pricing_order=self._line_env(order)['sale.order'].new(self._line_pricing_values(order,data)) if order.id and 'header' in data else order
                    values={'order_id':pricing_order.id or pricing_order,'product_id':product.id,'product_uom_qty':qty}
                    if data.get('uom_id'):
                        unit=self._line_choice(order,'uom',data['uom_id'])
                        if unit.category_id!=product.uom_id.category_id:raise ValidationError(_('Product and unit must have the same unit category.'))
                        values['product_uom']=unit.id
                    native=self._line_env(order)['sale.order.line'].new(values)
                    # Use the configured company default only if the product has
                    # no company tax. A fiscal position may intentionally remove it.
                    product_taxes=product.taxes_id.filtered(lambda t:t.company_id==order.company_id)
                    if not product_taxes and order.company_id.account_sale_tax_id:
                        native.tax_id=pricing_order.fiscal_position_id.map_tax(order.company_id.account_sale_tax_id)
                    result=self._line_data(native)
                elif operation=='preview':
                    self._editable(order)
                    raw=data.get('lines')
                    if not isinstance(raw,list) or len(raw)>200:raise ValidationError(_('Use at most 200 lines.'))
                    existing=set(order.order_line.ids);values=[]
                    for row in raw:
                        if not isinstance(row,dict) or (row.get('id') and self._line_id(row['id']) not in existing):
                            raise AccessError(_('Line is not available in this quotation.'))
                        values.append(self._line_values(order,row))
                    virtual=self._line_env(order)['sale.order'].new(dict(self._line_pricing_values(order,data),
                        order_line=[Command.create(dict(vals,sequence=(i+1)*10)) for i,vals in enumerate(values)]))
                    result={'untaxed':virtual.amount_untaxed,'tax':virtual.amount_tax,'total':virtual.amount_total,
                            'line_amounts':[l.price_subtotal for l in virtual.order_line]}
                elif operation=='create':
                    if order_id:raise AccessError(_('Use Save Lines for an existing quotation.'))
                    virtual,vals=self._line_new_order(data,required=True)
                    raw=data.get('lines')
                    if not isinstance(raw,list) or len(raw)>200:raise ValidationError(_('Use at most 200 lines.'))
                    commands=[]
                    for index,row in enumerate(raw):
                        if not isinstance(row,dict) or row.get('id'):raise ValidationError(_('Invalid new quotation line.'))
                        commands.append(Command.create(dict(self._line_values(virtual,row),sequence=(index+1)*10)))
                    order=self._line_env(virtual)['sale.order'].create(dict(vals,order_line=commands))
                    result=dict(self._line_boot(order),redirect='/my/employee/sales/%s'%order.id)
                elif operation=='save':
                    if not order_id:raise AccessError(_('Save the new quotation first.'))
                    # Parent and child locks protect ownership/state and all line versions.
                    request.env.cr.execute('SELECT id FROM sale_order WHERE id=%s FOR UPDATE',[order.id])
                    request.env.cr.execute('SELECT id FROM sale_order_line WHERE order_id=%s ORDER BY id FOR UPDATE',[order.id])
                    order.invalidate_recordset();order.order_line.invalidate_recordset();self._editable(order)
                    if not data.get('version') or data['version']!=self._line_version(order):
                        raise UserError(_('This quotation changed. Reload it before saving lines.'))
                    raw=data.get('lines')
                    if not isinstance(raw,list) or len(raw)>200:raise ValidationError(_('Use at most 200 lines.'))
                    commands=[];seen=set();existing={l.id:l for l in order.order_line}
                    for index,row in enumerate(raw):
                        if not isinstance(row,dict):raise ValidationError(_('Invalid line.'))
                        rid=self._line_id(row['id']) if row.get('id') else 0
                        if rid and (rid not in existing or rid in seen):raise AccessError(_('Line is not available in this quotation.'))
                        if rid:seen.add(rid)
                        if rid and existing[rid].product_id and not row.get('product_id') and not row.get('display_type'):
                            raise ValidationError(_('Choose a product from the list.'))
                        vals=self._line_values(order,row)
                        if rid and (existing[rid].display_type or False)!=(vals.get('display_type') or False):
                            raise ValidationError(_('Remove and add a line to change its type.'))
                        vals['sequence']=(index+1)*10
                        commands.append(Command.update(rid,vals) if rid else Command.create(vals))
                    commands += [Command.delete(rid) for rid in existing if rid not in seen]
                    # Enroll editable native drafts in the existing issuer workflow.
                    if not order.absar_portal_creator_id:
                        order._absar_review_write({'absar_portal_creator_id':request.env.uid,'absar_portal_review_state':'draft'})
                    values=self._line_header_values(order,data['header']) if 'header' in data else {}
                    order.write(dict(values,order_line=commands))
                    result=self._line_boot(order)
                else:raise AccessError(_('Unsupported operation.'))
            return request.make_json_response({'ok':True,'result':result})
        except (AccessError,UserError,ValidationError,Forbidden,NotFound,ValueError,TypeError,OverflowError) as exc:
            return request.make_json_response({'ok':False,'error':str(exc)},status=400)
