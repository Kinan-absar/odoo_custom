from copy import deepcopy
from odoo import Command
from odoo.exceptions import AccessError
from werkzeug.exceptions import Forbidden
from types import SimpleNamespace
from lxml import etree
from odoo.http import Response


def run(env, f):
    company,user,service,deny=f['company'],f['user'],f['service'],f['deny']
    bill,pay,receipt,journal=f['bill'],f['pay'],f['receipt'],f['journal']
    normal=user('direct-accounting-user','accountant');direct=service(normal)
    assert normal.share and not normal.has_group('base.group_user')
    assert not env['account.move'].with_user(normal).has_access('create')
    assert direct._actor()[1]['direct']
    created=direct._save(company,'bills',dict(bill,ref='DIRECT-NORMAL-BILL',post=True))
    move=env['account.move'].browse(created['id'])
    assert move.state=='posted' and not move.portal_accounting_review_required
    assert move.create_uid==normal and move.write_uid==normal
    assert not move.portal_accounting_reviewer_id
    notes=move.message_ids.filtered(lambda m:'Accounting:' in str(m.body))
    assert notes and all(n.author_id==normal.partner_id for n in notes)
    assert any('post' in str(n.body) for n in notes)
    assert created['history'] and not created['editable']
    deny(lambda:direct._save(company,'bills',dict(bill,id=move.id,version=str(move.write_date))))
    pending=direct._act(company,'bills',move.id,'reset',{'version':str(move.write_date),'comment':'Correct expense classification'})
    assert move.state=='posted' and pending['portal_accounting_reset_pending']
    assert move.portal_accounting_reset_requested_by==normal
    assert move.activity_ids and all(not a.user_id.share for a in move.activity_ids)
    deny(lambda:direct._act(company,'bills',move.id,'reset',{'version':str(move.write_date),'comment':'Duplicate'}))
    for kind,data in [('journals',dict(journal,ref='DIRECT-JV')),('payments',dict(pay,bill_ids=[])),('receipts',dict(receipt,invoice_ids=[]))]:
        result=direct._save(company,kind,dict(data,post=True))
        record=env[{'journals':'account.move','payments':'account.payment.voucher','receipts':'account.receipt.voucher'}[kind]].browse(result['id'])
        assert record.state=='posted' and not record.portal_accounting_review_required
        assert record.create_uid==normal
        if kind!='journals':
            assert record.move_id.state=='posted'
            direct._act(company,kind,record.id,'request-reset',{'version':str(record.write_date),'comment':'Permission only'})
            assert record.state=='posted' and record.portal_accounting_reset_pending
            deny(lambda:record.write({'amount':1}))
    colleague=user('direct-accounting-colleague','accountant')
    shared=service(colleague)._save(company,'bills',dict(bill,ref='SHARED-ORDINARY-DRAFT'))
    assert direct._detail(company,'bills',shared['id'])['editable']
    shared=direct._save(company,'bills',dict(bill,id=shared['id'],version=shared['version'],ref='SHARED-ORDINARY-DRAFT',post=True))
    shared_move=env['account.move'].browse(shared['id'])
    assert shared_move.state=='posted' and shared_move.create_uid==colleague and shared_move.write_uid==normal
    normal.groups_id=[Command.link(env.ref('absar_portal_accounting.group_preparer').id)]
    assert not direct._actor()[1]['direct']
    deny(lambda:direct._save(company,'bills',dict(bill,ref='NO-DIRECT-FOR-PREPARER',post=True)))
    print('PASS: direct portal bill/JV/PV/RV posting, real actor create/write/chatter identity, posted immutability, permission-only resets, pending internal activities and preparer precedence.',flush=True)

    native=env['res.users'].with_context(no_reset_password=True).create({'name':'Ordinary Native Accountant','login':'ordinary-native-accountant',
        'company_id':company.id,'company_ids':[Command.set(company.ids)],'groups_id':[Command.set([env.ref('base.group_user').id,env.ref('account.group_account_user').id])]})
    raw=f['prep']._move_values(company,'bills',dict(bill,ref='ORDINARY-NATIVE-DIRECT'))
    ordinary=env['account.move'].with_user(native).create(raw);ordinary.action_post()
    assert ordinary.state=='posted' and not ordinary.portal_accounting_review_required
    # The same internal employee is restricted only after explicit group assignment.
    native.groups_id=[Command.link(env.ref('absar_portal_accounting.group_preparer').id),Command.link(env.ref('absar_portal_accounting.group_approver').id)]
    raw=f['prep']._move_values(company,'bills',dict(bill,ref='RESTRICTED-NATIVE'))
    restricted=env['account.move'].with_user(native).create(raw)
    restricted.with_context(_absar_accounting_action=True).action_post()
    assert restricted.state=='draft' and restricted.portal_accounting_review_required and restricted.portal_accounting_review=='submitted'
    deny(lambda:restricted.action_portal_accounting_approve())
    deny(lambda:restricted.write({'portal_accounting_review_required':False}))
    deny(lambda:env['account.move'].with_user(native).create(dict(raw,portal_accounting_review='approved')))
    approver=env['res.users'].with_context(no_reset_password=True).create({'name':'Backend Accounting Reviewer','login':'backend-accounting-reviewer',
        'company_id':company.id,'company_ids':[Command.set(company.ids)],'groups_id':[Command.set([env.ref('base.group_user').id,env.ref('account.group_account_user').id,env.ref('absar_portal_accounting.group_approver').id])]})
    view=etree.fromstring(env['account.move'].with_user(approver).get_view(env.ref('account.view_move_form').id,'form')['arch'])
    assert view.xpath("//header/button[@name='action_portal_accounting_approve']")
    assert not view.xpath("//a[contains(text(),'Open Accounting Workspace')]")
    reviewed=restricted.with_user(approver)
    assert reviewed.portal_accounting_can_review
    reviewed.portal_accounting_comment='Correct reference';reviewed.action_portal_accounting_return()
    assert restricted.portal_accounting_review=='returned'
    restricted.action_portal_accounting_submit();reviewed.action_portal_accounting_approve()
    assert restricted.state=='posted' and restricted.portal_accounting_reviewer_id==approver
    portal_sub=f['prep']._save(company,'bills',dict(bill,ref='PORTAL-TO-NATIVE',submit=True))
    env['account.move'].browse(portal_sub['id']).with_user(approver).action_portal_accounting_approve()
    assert env['account.move'].browse(portal_sub['id']).state=='posted'
    approver.groups_id=[Command.link(env.ref('absar_portal_accounting.group_preparer').id),Command.link(env.ref('internal_transfer_voucher.group_weekly_payment_plan_manager').id)]
    voucher=f['prep']._save(company,'payments',dict(pay,amount=12,bill_ids=[],submit=True))
    native_voucher=env['account.payment.voucher'].browse(voucher['id']).with_user(approver)
    native_voucher.action_portal_accounting_approve()
    assert native_voucher.state=='posted' and native_voucher.move_id.state=='posted'
    assert not native_voucher.move_id.portal_accounting_review_required
    # An actual native overpayment remains a draft until its warning is acknowledged.
    over=f['prep']._save(company,'payments',dict(pay,amount=1000,bill_ids=[],purchase_order_ids=f['po'].ids,submit=True))
    over=env['account.payment.voucher'].browse(over['id']).with_user(approver)
    action=over.action_portal_accounting_approve()
    assert over.state=='draft' and action['res_model']=='absar.accounting.post.confirm'
    wizard=env['absar.accounting.post.confirm'].with_user(approver).browse(action['res_id'])
    assert 'PO OVERPAYMENT:' in wizard.warning
    wizard.confirm_overpayment=True;wizard.action_confirm()
    assert over.state=='posted' and over.move_id.state=='posted'
    deny(lambda:env['absar.accounting.post.confirm'].with_user(f['issuer']).create({'kind':'bills','record_id':move.id,'version':str(move.write_date)}))
    print('PASS: combined native preparer/approver posts someone else’s voucher without double review; real native overpayment warning/confirmation; portal users cannot create the backend wizard.',flush=True)
    print('PASS: ordinary native accountants post without enrollment; restricted native submission; self-approval/metadata/context bypass denied; native return/approve handles native and portal issuers.',flush=True)

    # Portal route boundaries and exact JV report target, without executing a live PDF renderer.
    import odoo.addons.absar_portal_accounting.controllers.portal as module
    controller=module.PortalAccounting();original=module.request
    internal_request=SimpleNamespace(env=env(user=approver.id),redirect=lambda url:Response(status=303,headers={'Location':url}))
    module.request=internal_request
    try:
        assert controller.home().headers['Location']=='/odoo'
        assert controller.listing('bills').headers['Location']=='/odoo'
        try:controller._service()
        except Forbidden:pass
        else:raise AssertionError('Internal portal API must be blocked')
    finally:module.request=original
    report_class=type(env['ir.actions.report']);original_pdf=report_class._render_qweb_pdf;calls=[]
    report_class._render_qweb_pdf=lambda self,ref,res_ids=None,**kw:(calls.append((ref,res_ids)) or (b'%PDF-test','pdf'))
    module.request=SimpleNamespace(env=env(user=f['issuer'].id),make_response=lambda data,headers:Response(data,headers=headers))
    try:
        controller.print_record('bills',f['move'].id,company_id=company.id,journal_entry='1')
        assert calls[-1]==('absar_portal_accounting.report_journal',f['move'].ids)
        controller.print_record('payments',f['pv'].id,company_id=company.id,journal_entry='1')
        assert calls[-1]==('absar_portal_accounting.report_journal',f['pv'].move_id.ids)
    finally:module.request=original;report_class._render_qweb_pdf=original_pdf
    print('PASS: internal users redirected to backend, portal API blocked for internal users, bill/voucher JV print routes target actual account.move entries.',flush=True)
