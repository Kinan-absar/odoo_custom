from copy import deepcopy
from types import SimpleNamespace
from odoo import fields, Command
from odoo.exceptions import AccessError, UserError, ValidationError
from lxml import etree
from pathlib import Path


def run(env):
    company = env.company
    sar = env.ref('base.SAR'); sar.active = True
    company.write({'currency_id': sar.id, 'country_id': env.ref('base.sa').id, 'account_fiscal_country_id': env.ref('base.sa').id})
    def account(code, name, typ, reconcile=False, comp=company):
        return env['account.account'].create({'code': code, 'name': name, 'account_type': typ,
                                             'reconcile': reconcile, 'company_ids': [Command.set(comp.ids)]})
    expense = account('610001', 'Test Materials', 'expense')
    revenue = account('510001', 'Test Revenue', 'income')
    payable = account('210001', 'Test Payable', 'liability_payable', True)
    receivable = account('110001', 'Test Receivable', 'asset_receivable', True)
    bank = account('110002', 'Test Bank', 'asset_cash')
    vat = account('110003', 'Test VAT', 'asset_current')
    bank2 = account('110004', 'Test Bank 2', 'asset_cash')
    purchase = env['account.journal'].create({'name':'Test Purchases','code':'TPUR','type':'purchase','company_id':company.id,'default_account_id':expense.id})
    misc = env['account.journal'].create({'name':'Test Misc','code':'TMIS','type':'general','company_id':company.id,'default_account_id':expense.id})
    cash = env['account.journal'].create({'name':'Test Bank','code':'TBAN','type':'bank','company_id':company.id,'default_account_id':bank.id})
    cash2 = env['account.journal'].create({'name':'Test Bank 2','code':'TB2','type':'bank','company_id':company.id,'default_account_id':bank2.id})
    sale = env['account.journal'].create({'name':'Test Sales','code':'TSAL','type':'sale','company_id':company.id,'default_account_id':revenue.id})
    vendor=env['res.partner'].create({'name':'Disposable Accounting Vendor','supplier_rank':1,
        'property_account_payable_id':payable.id,'property_account_receivable_id':receivable.id})
    taxgroup=env['account.tax.group'].create({'name':'Test VAT','country_id':env.ref('base.sa').id})
    tax=env['account.tax'].create({'name':'Test VAT 15%','amount':15,'amount_type':'percent','type_tax_use':'purchase',
        'company_id':company.id,'tax_group_id':taxgroup.id,
        'invoice_repartition_line_ids':[Command.create({'repartition_type':'base'}),Command.create({'repartition_type':'tax','account_id':vat.id})],
        'refund_repartition_line_ids':[Command.create({'repartition_type':'base'}),Command.create({'repartition_type':'tax','account_id':vat.id})]})
    product=env['product.product'].create({'name':'Test Materials','type':'consu','purchase_method':'purchase',
        'property_account_expense_id':expense.id,'supplier_taxes_id':[Command.set(tax.ids)]})
    def user(name, role=None, ceo=False):
        groups=[env.ref('base.group_portal').id]
        if role: groups.append(env.ref('absar_portal_accounting.group_'+role).id)
        if ceo: groups.append(env.ref('employee_portal_suite.group_employee_portal_ceo').id)
        u=env['res.users'].with_context(no_reset_password=True).create({'name':name,'login':name,
            'company_id':company.id,'company_ids':[Command.set(company.ids)],'groups_id':[Command.set(groups)]})
        env['hr.employee'].create({'name':name,'user_id':u.id,'company_id':company.id})
        return u
    issuer=user('accounting-issuer','preparer'); reviewer=user('accounting-reviewer','approver')
    monitor=user('accounting-monitor','monitor'); outsider=user('accounting-outsider')
    ceo=user('accounting-ceo','monitor',True)
    def service(u):return env['absar.portal.accounting.service'].with_user(u).with_context(allowed_company_ids=company.ids)
    prep,approve,watch=service(issuer),service(reviewer),service(monitor)
    def deny(fn):
        try:
            with env.cr.savepoint():fn()
        except (AccessError,UserError,ValidationError):return
        raise AssertionError('Operation should have been rejected')
    def check(value,want):assert abs(value-want)<0.001,(value,want)
    bill={'journal_id':purchase.id,'partner_id':vendor.id,'currency_id':sar.id,'date':'2026-10-19',
          'invoice_date':'2026-10-19','ref':'TEST-BILL-001','lines':[{'name':'Materials','product_id':product.id,
          'quantity':2,'price_unit':100,'account_id':expense.id,'taxes_id':tax.ids}]}
    deny(lambda:prep._save(company,'bills',bill))
    assert watch._list(company,'bills')['count']==0
    company.portal_accounting_journal_ids=[Command.set((purchase|misc|cash|cash2).ids)]
    deny(lambda:service(outsider)._list(company,'bills'))
    deny(lambda:watch._save(company,'bills',bill))
    deny(lambda:approve._save(company,'bills',bill))
    for u in (issuer,reviewer,monitor,ceo):
        assert u.share and not u.has_group('base.group_user') and not u.has_group('account.group_account_user')
        assert not env['account.move'].with_user(u).check_access_rights('create',raise_exception=False)
    before=env['account.move'].search_count([])
    preview=prep._preview(company,'bills',bill)
    check(preview['total'],230);check(preview['tax'],30)
    included=tax.copy({'name':'Test VAT Included','price_include_override':'tax_included'})
    included_bill=deepcopy(bill);included_bill['lines'][0].update(price_unit=115,taxes_id=included.ids)
    included_preview=prep._preview(company,'bills',included_bill)
    check(included_preview['untaxed'],200);check(included_preview['total'],230);check(included_preview['line_amounts'][0],200)
    assert env['account.move'].search_count([])==before
    saved=prep._save(company,'bills',bill)
    move=env['account.move'].browse(saved['id']);check(move.amount_total,230)
    assert move.create_uid==issuer and move.portal_accounting_issuer_id==issuer
    denied_copy=deepcopy(bill);denied_copy['move_type']='out_invoice'
    # An injected move_type is ignored; only the explicit vendor-bill kind controls it.
    assert prep._move_values(company,'bills',denied_copy)['move_type']=='in_invoice'
    deny(lambda:prep._save(company,'invoices',bill))
    deny(lambda:watch._options(company,'invoice',kind='bills',partner_id=vendor.id))
    deny(lambda:prep._save(company,'bills',dict(bill,journal_id=sale.id)))
    deny(lambda:prep._save(company,'bills',dict(bill,id=move.id,version='outdated')))
    submitted=prep._act(company,'bills',move.id,'submit',{'version':saved['version']})
    assert move.state=='draft' and move.portal_accounting_review=='submitted'
    deny(lambda:move._post())
    deny(lambda:move.action_post()) # native posting cannot bypass required review
    assert move.state=='draft' and move.portal_accounting_review=='submitted'
    deny(lambda:prep._act(company,'bills',move.id,'post',{'version':submitted['version']}))
    issuer.groups_id=[Command.link(env.ref('absar_portal_accounting.group_approver').id)]
    deny(lambda:prep._act(company,'bills',move.id,'post',{'version':submitted['version']}))
    issuer.groups_id=[Command.unlink(env.ref('absar_portal_accounting.group_approver').id)]
    deny(lambda:watch._act(company,'bills',move.id,'post',{'version':submitted['version']}))
    returned=approve._act(company,'bills',move.id,'return',{'version':submitted['version'],'comment':'Check quantity'})
    assert returned['review']=='returned'
    edited=prep._save(company,'bills',dict(bill,id=move.id,version=returned['version']))
    submitted=prep._act(company,'bills',move.id,'submit',{'version':edited['version']})
    posted=approve._act(company,'bills',move.id,'post',{'version':submitted['version']})
    assert posted['state']=='posted' and move.portal_accounting_reviewer_id==reviewer
    check(sum(move.line_ids.mapped('debit')),sum(move.line_ids.mapped('credit')))
    assert move.portal_accounting_review=='approved'
    deny(lambda:prep._save(company,'bills',dict(bill,id=move.id,version=posted['version'])))
    print('PASS: actual bill preview (230 including VAT), draft/return/resubmit/post, native posting guard, no sales invoices or generic portal accounting ACLs.',flush=True)

    # Independent company/journal and relation boundaries.
    other=env['res.company'].create({'name':'Other test company','currency_id':sar.id})
    foreign=account('990001','Foreign Expense','expense',comp=other)
    deny(lambda:prep._company(other.id))
    bad=deepcopy(bill);bad['lines'][0]['account_id']=foreign.id
    deny(lambda:prep._save(company,'bills',bad))
    bad=deepcopy(bill);bad['lines'][0]['price_unit']='NaN'
    deny(lambda:prep._save(company,'bills',bad))
    bad=deepcopy(bill);bad['lines'][0]['analytic_distribution']={str(foreign.id):101}
    deny(lambda:prep._save(company,'bills',bad))
    duplicate=prep._save(company,'bills',dict(bill,submit=True))
    deny(lambda:approve._act(company,'bills',duplicate['id'],'post',{'version':duplicate['version']}))
    assert env['account.move'].browse(duplicate['id']).state=='draft'
    # Native child edits invalidate submitted reviews.
    moved=env['account.move'].browse(duplicate['id']);moved.invoice_line_ids[0].write({'name':'Native correction'})
    assert moved.portal_accounting_review=='returned'
    print('PASS: cross-company/account/journal denial, non-finite values, duplicate vendor reference and native child edit invalidation.',flush=True)

    journal={'journal_id':misc.id,'date':'2026-10-19','currency_id':sar.id,'ref':'TEST JOURNAL','lines':[
        {'name':'Debit','account_id':expense.id,'debit':100,'credit':0},
        {'name':'Credit','account_id':bank.id,'debit':0,'credit':100}]}
    bad=deepcopy(journal);bad['lines'][1]['credit']=90
    deny(lambda:prep._save(company,'journals',bad))
    entry=prep._save(company,'journals',dict(journal,submit=True))
    entry=approve._act(company,'journals',entry['id'],'post',{'version':entry['version']})
    assert entry['state']=='posted'
    refund=prep._save(company,'refunds',dict(bill,ref='CREDIT-001',submit=True))
    refund=approve._act(company,'refunds',refund['id'],'post',{'version':refund['version']})
    assert refund['state']=='posted'
    print('PASS: balanced miscellaneous entry, unbalanced entry rejection and vendor credit-note posting.',flush=True)

    pay={'journal_id':cash.id,'account_id':payable.id,'partner_id':vendor.id,'amount':230,'date':'2026-10-19',
        'currency_id':sar.id,'payment_method':'bank_transfer','bill_ids':move.ids}
    voucher=prep._save(company,'payments',dict(pay,submit=True))
    voucher=approve._act(company,'payments',voucher['id'],'post',{'version':voucher['version']})
    pv=env['account.payment.voucher'].browse(voucher['id'])
    assert pv.state=='posted' and pv.move_id.state=='posted' and pv.cash_plan_line_id.is_unplanned
    voucher=approve._act(company,'payments',pv.id,'reconcile',{'version':voucher['version']})
    check(move.amount_residual,0)
    voucher=approve._act(company,'payments',pv.id,'unreconcile',{'version':voucher['version']})
    check(move.amount_residual,230)
    # Existing customer invoice is only used as a receipt matching fixture.
    invoice=env['account.move'].create({'move_type':'out_invoice','journal_id':sale.id,'partner_id':vendor.id,
        'invoice_date':'2026-10-19','date':'2026-10-19','invoice_line_ids':[Command.create({'name':'Existing receivable',
        'quantity':1,'price_unit':120,'account_id':revenue.id,'tax_ids':[Command.clear()]})]})
    invoice.action_post()
    receipt={'journal_id':cash.id,'account_id':receivable.id,'partner_id':vendor.id,'amount':120,
             'date':'2026-10-19','currency_id':sar.id,'receipt_method':'bank_transfer','invoice_ids':invoice.ids}
    rv=prep._save(company,'receipts',dict(receipt,submit=True))
    rv=approve._act(company,'receipts',rv['id'],'post',{'version':rv['version']})
    rv=approve._act(company,'receipts',rv['id'],'reconcile',{'version':rv['version']})
    check(invoice.amount_residual,0)
    rv=approve._act(company,'receipts',rv['id'],'unreconcile',{'version':rv['version']})
    check(invoice.amount_residual,120)
    assert watch._options(company,'invoice',kind='receipts',partner_id=vendor.id)
    transfer=dict(pay,account_id=False,payment_method='journal_transfer',bill_ids=[],amount=50,
                  destinations=[{'journal_id':cash2.id,'amount':50}])
    transfer=prep._save(company,'payments',dict(transfer,submit=True))
    transfer=approve._act(company,'payments',transfer['id'],'post',{'version':transfer['version']})
    assert transfer['state']=='posted'
    print('PASS: real payment/receipt vouchers, posted journal entries, reconciliation/unreconciliation, unplanned actual link and journal transfer.',flush=True)

    category=env['cash.plan.category'].create({'name':'Test Supplier','flow_type':'out','company_id':company.id})
    run=env['cash.plan.run'].create({'date_from':'2026-10-19','date_to':'2026-10-25','company_id':company.id})
    plan={'name':'Test Planned Payment','partner_id':vendor.id,'category_id':category.id,'forecast_amount':100,
          'journal_id':cash.id,'account_id':payable.id,'transaction_type':'supplier'}
    planned=prep._save(company,'planned',dict(plan,submit=True))
    line=env['cash.plan.line'].browse(planned['id'])
    assert line.ceo_decision=='pending' and line.state=='planned'
    deny(lambda:prep._save(company,'planned',dict(plan,id=line.id,version=planned['version'])))
    deny(lambda:approve._act(company,'planned',line.id,'approve',{'version':planned['version'],'approved_amount':100}))
    planned=service(ceo)._act(company,'planned',line.id,'add-plan',{'version':planned['version'],'run_id':run.id})
    planned=service(ceo)._act(company,'planned',line.id,'approve',{'version':planned['version'],'approved_amount':90})
    assert line.ceo_decision=='adjusted' and line.state=='approved'
    deny(lambda:prep._act(company,'planned',line.id,'mark-paid',{'version':planned['version']}))
    line.action_mark_as_paid() # existing INTERNAL execution path, fixture superuser only
    result=prep._act(company,'planned',line.id,'create-voucher',{'version':str(line.write_date)})
    assert result['redirect'] and line.payment_voucher_id.state=='draft'
    check(line.payment_voucher_id.amount,90)
    assert line.payment_voucher_id.portal_accounting_issuer_id==issuer
    print('PASS: native planned-payment CEO submission/adjustment/weekly plan, editing lock, internal-only execution and draft voucher handoff.',flush=True)

    po=env['purchase.order'].create({'partner_id':vendor.id,'company_id':company.id,'order_line':[Command.create({
        'product_id':product.id,'name':'PO Test Materials','product_qty':3,'product_uom':product.uom_id.id,
        'price_unit':100,'date_planned':'2026-10-19 10:00:00','taxes_id':[Command.set(tax.ids)]})]})
    po.button_confirm()
    imported=prep._po_lines(company,po.id)
    check(imported['lines'][0]['quantity'],3)
    pb=prep._save(company,'bills',dict(bill,ref='PO-BILL',lines=imported['lines']))
    assert env['account.move'].browse(pb['id']).invoice_line_ids.purchase_line_id==po.order_line
    print('PASS: PO bill-control quantity import and actual purchase line linking.',flush=True)

    # Actual portal templates render against minimally substituted EPS outer layout.
    import json
    import odoo.addons.absar_portal_accounting.controllers.portal as controller
    from urllib.parse import quote_plus
    class FakeRequest:
        def __init__(self,u):self.env=env(user=u.id);self.httprequest=SimpleNamespace(path='/my/employee/accounting')
        def csrf_token(self,*args,**kwargs):return 'isolated-test-token'
    vals={'company':company,'companies':company,'roles':{'preparer':True,'approver':False,'monitor':False},
          'kinds':__import__('odoo.addons.absar_portal_accounting.models.service',fromlist=['KINDS']).KINDS,
          'configured':True,'quote_plus':quote_plus,'request':FakeRequest(issuer)}
    vals.update(prep._list(company,'bills'),kind='bills',title='Vendor Bills',q='',status='',message='')
    html=env['ir.qweb']._render('absar_portal_accounting.listing',vals,minimal_qcontext=True)
    assert 'Vendor Bills' in str(html) and 'aca-table' in str(html)
    vals.update(boot_json=json.dumps(watch._detail(company,'bills',move.id)))
    detail_html=env['ir.qweb']._render('absar_portal_accounting.detail',vals,minimal_qcontext=True)
    assert 'aca-editor' in str(detail_html) and 'data-csrf=' in str(detail_html)
    vals.update(counts={k:0 for k in vals['kinds']})
    assert 'Accounting Workspace' in str(env['ir.qweb']._render('absar_portal_accounting.home',vals,minimal_qcontext=True))
    report_html,typ=env['ir.actions.report']._render_qweb_html('absar_portal_accounting.report_journal',[entry['id']])
    assert b'Journal Voucher' in report_html
    print('PASS: actual inherited backend views and portal list templates load/render; all fixtures rolled back.',flush=True)

    # Route-level validation and transactional rollback after an actual ORM create.
    http=controller.PortalAccounting()
    real_request=controller.request
    controller.request=SimpleNamespace(env=env(user=issuer.id),httprequest=SimpleNamespace(content_length=100),
        make_json_response=lambda body,status=200:dict(body,status=status))
    try:
        route_payload=dict(bill,kind='bills',company_id=company.id,ref='HTTP-BILL')
        response=http.api.__wrapped__(http,'save',payload=json.dumps(route_payload))
        assert response['ok'] and response['status']==200
        deny(lambda:watch._record(company,'bills',pv.id+100000))
        response=http.api.__wrapped__(http,'save',payload=json.dumps(dict(route_payload,kind='invoices')))
        assert not response['ok']
        old_count=env['account.move'].search_count([])
        # Force failure after create via invalid submission of a receipt plan.
        incoming=env['cash.plan.category'].create({'name':'Test Receipt','flow_type':'in','company_id':company.id})
        incoming_payload=dict(plan,kind='planned-receipts',company_id=company.id,category_id=incoming.id,submit=True)
        plan_count=env['cash.plan.line'].search_count([])
        response=http.api.__wrapped__(http,'save',payload=json.dumps(incoming_payload))
        assert not response['ok'] and env['cash.plan.line'].search_count([])==plan_count
    finally:controller.request=real_request
    print('PASS: actual HTTP controller dispatch, sales-invoice route denial and savepoint rollback after ORM creation.',flush=True)

    # Posted-voucher reset delegates to existing native reconciliation checks.
    voucher=approve._act(company,'payments',pv.id,'reset',{'version':str(pv.write_date),'comment':'Test corrected allocation'})
    assert pv.state=='posted' and voucher['portal_accounting_reset_pending']
    assert pv.portal_accounting_reset_requested_by==reviewer
    dollar=env.ref('base.USD');dollar.active=True
    deny(lambda:prep._save(company,'payments',dict(pay,currency_id=dollar.id)))
    transfer_draft=prep._save(company,'payments',dict(pay,payment_method='journal_transfer',account_id=False,bill_ids=[],
        amount=50,destinations=[{'journal_id':cash2.id,'amount':50}],submit=True))
    tv=env['account.payment.voucher'].browse(transfer_draft['id'])
    tv.line_ids[0].write({'amount':50})
    assert tv.portal_accounting_review=='returned'
    print('PASS: permission-only posted-voucher reset request, company-currency voucher guard and child-allocation review invalidation.',flush=True)

    internal=env['res.users'].with_context(no_reset_password=True).create({'name':'Native Accounting Issuer','login':'native-accounting-issuer',
        'company_id':company.id,'company_ids':[Command.set(company.ids)],'groups_id':[Command.set([
        env.ref('base.group_user').id,env.ref('account.group_account_user').id])]})
    internal.groups_id=[Command.link(env.ref('absar_portal_accounting.group_preparer').id)]
    raw=prep._move_values(company,'bills',dict(bill,ref='NATIVE-BILL'))
    native=env['account.move'].with_user(internal).create(raw)
    result=native.action_post()
    assert result['tag']=='display_notification' and native.state=='draft' and native.portal_accounting_review=='submitted'
    assert native.portal_accounting_issuer_id==internal
    native=approve._act(company,'bills',native.id,'post',{'version':str(native.write_date)})
    assert native['state']=='posted'
    raw=prep._move_values(company,'journals',dict(journal,ref='NATIVE-JOURNAL'))
    native=env['account.move'].with_user(internal).create(raw)
    native.action_post()
    assert native.state=='draft' and native.portal_accounting_review=='submitted'
    native_posted=approve._act(company,'journals',native.id,'post',{'version':str(native.write_date)})
    assert native_posted['state']=='posted'
    for kind,model,data in [('payments','account.payment.voucher',pay),('receipts','account.receipt.voucher',receipt)]:
        # The existing voucher module's unplanned-actual hook requires its
        # existing planning role for native users (no portal grant is added).
        internal.groups_id=[Command.link(env.ref('internal_transfer_voucher.group_weekly_payment_plan_manager').id)]
        raw=prep._voucher_values(company,kind,data)
        native_voucher=env[model].with_user(internal).create(raw)
        native_voucher.action_post()
        assert native_voucher.state=='draft' and native_voucher.portal_accounting_review=='submitted'
        result=approve._act(company,kind,native_voucher.id,'post',{'version':str(native_voucher.write_date)})
        assert result['state']=='posted' and native_voucher.move_id.state=='posted'
    print('PASS: actual native internal bill, miscellaneous entry, payment voucher and receipt voucher first-post submit -> shared portal approval -> posted; no double review of generated voucher entries.',flush=True)

    first=prep._save(company,'planned',dict(plan,name='Bulk first'))
    second=prep._save(company,'planned',dict(plan,name='Bulk second'))
    assert prep._submit_selected(company,[{'id':first['id'],'version':first['version']},{'id':second['id'],'version':second['version']}])==2
    assert env['cash.plan.line'].browse([first['id'],second['id']]).mapped('ceo_decision')==['pending','pending']
    third=prep._save(company,'planned',dict(plan,name='Bulk valid third'))
    deny(lambda:prep._submit_selected(company,[{'id':third['id'],'version':third['version']},{'id':first['id'],'version':str(env['cash.plan.line'].browse(first['id']).write_date)}]))
    assert env['cash.plan.line'].browse(third['id']).ceo_decision=='not_sent'
    print('PASS: planned payment bulk submit validates the full selection and preserves all-or-nothing behavior.',flush=True)
    internal.groups_id=[Command.link(env.ref('internal_transfer_voucher.group_payment_execution_manager').id)]
    reset_line=env['cash.plan.line'].browse(second['id'])
    reset=prep._act(company,'planned',reset_line.id,'request-reset',{'version':str(reset_line.write_date)})
    assert reset_line.reset_request_pending and reset_line.ceo_decision=='pending' and not reset['editable']
    print('PASS: portal reset request preserves the existing internal execution-manager approval requirement.',flush=True)
    partner_bank=env['res.partner.bank'].create({'partner_id':vendor.id,'acc_number':'TEST-ACCOUNT-123','company_id':company.id})
    assert prep._options(company,'bank',query='123',kind='bills',partner_id=vendor.id)[0]['id']==partner_bank.id
    overpayment=prep._save(company,'payments',dict(pay,amount=500,bill_ids=[],purchase_order_ids=po.ids,submit=True))
    deny(lambda:approve._act(company,'payments',overpayment['id'],'post',{'version':overpayment['version']}))
    ov=env['account.payment.voucher'].browse(overpayment['id'])
    assert ov.state=='draft' and ov.portal_accounting_review=='submitted'
    overpayment=approve._act(company,'payments',ov.id,'post',{'version':str(ov.write_date),'confirm_overpayment':True})
    assert overpayment['state']=='posted'
    fee=prep._save(company,'payments',dict(pay,amount=100,bill_ids=[],account_id=expense.id,has_bank_fees=True,
        fee_amount=10,fee_account_id=expense.id,fee_tax_id=tax.id,submit=True))
    fee=approve._act(company,'payments',fee['id'],'post',{'version':fee['version']})
    fee_move=env['account.payment.voucher'].browse(fee['id']).move_id
    check(sum(fee_move.line_ids.mapped('debit')),111.5)
    check(sum(fee_move.line_ids.mapped('credit')),111.5)
    print('PASS: recipient bank search, explicit native PO-overpayment confirmation and bank-fee VAT balanced posting.',flush=True)
    from roles_cases import run as run_roles
    run_roles(env, locals())
    mandatory_plan=env['account.analytic.plan'].create({'name':'Required Test Plan','default_applicability':'mandatory'})
    env['account.analytic.account'].create({'name':'Required Test Account','plan_id':mandatory_plan.id,'company_id':company.id})
    mandatory=prep._save(company,'bills',dict(bill,ref='MANDATORY-ANALYTIC',submit=True))
    deny(lambda:approve._act(company,'bills',mandatory['id'],'post',{'version':mandatory['version']}))
    assert env['account.move'].browse(mandatory['id']).state=='draft'
    print('PASS: native mandatory analytic-plan validation remains enforced before portal posting.',flush=True)
    native_arch=etree.fromstring(env['account.move'].get_view(env.ref('account.view_move_form').id,'form')['arch'])
    post_buttons=native_arch.xpath("//header/button[@name='action_post']")
    assert len(post_buttons)==2 and all('portal_accounting_requires_review' in b.get('invisible','') for b in post_buttons)
    print('PASS: both native entry Post and bill Confirm buttons use the shared review visibility condition.',flush=True)

    from design_cases import run as run_design
    run_design(env)
