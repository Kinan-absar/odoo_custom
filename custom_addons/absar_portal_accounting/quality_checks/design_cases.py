from types import SimpleNamespace
from urllib.parse import quote_plus
from lxml import etree


def run(env):
    Company=env['res.company']; Journal=env['account.journal']; Settings=env['res.config.settings']
    company=Company.create({'name':'Design QA Company','currency_id':env.company.currency_id.id})
    other=Company.create({'name':'Design QA Other Company','currency_id':env.company.currency_id.id})
    journal=Journal.create({'name':'Design QA Purchases','code':'DQA','type':'purchase','company_id':company.id})
    company.portal_accounting_journal_ids=journal
    settings=Settings.with_company(company).create({'company_id':company.id})
    assert settings.portal_accounting_journal_ids==journal
    settings.portal_accounting_review_internal=False
    assert not company.portal_accounting_review_internal
    settings.portal_accounting_journal_ids=[(5,0,0)]
    assert not company.portal_accounting_journal_ids
    settings.portal_accounting_journal_ids=[(6,0,journal.ids)]
    assert company.portal_accounting_journal_ids==journal
    assert not Settings.with_company(other).create({'company_id':other.id}).portal_accounting_journal_ids
    old=env.ref('absar_portal_accounting.company_portal_accounting')
    assert not old.active
    combined=etree.fromstring(env['res.config.settings'].get_view(view_id=env.ref('account.res_config_settings_view_form').id,view_type='form')['arch'])
    assert len(combined.xpath("//app[@name='account']/block[@name='employee_portal_accounting']"))==1
    assert len(combined.xpath("//setting[@id='portal_accounting_journals']/field[@name='portal_accounting_journal_ids']"))==1
    assert not combined.xpath("//setting[@id='portal_accounting_internal_review']")
    native=etree.fromstring(env['account.move'].get_view(env.ref('account.view_move_form').id,'form')['arch'])
    assert not native.xpath("//a[contains(text(),'Open Accounting Workspace')]")
    inherited=etree.fromstring(env.ref('absar_portal_accounting.move_portal_review').arch_db)
    assert inherited.xpath("//button[@name='action_portal_accounting_approve']")
    assert env['res.config.settings']._fields['portal_accounting_journal_ids'].groups=='base.group_system'
    print('PASS: settings view registry, existing journal selections retained, related settings persist to company, company isolation and legacy tab deactivated.',flush=True)
    from odoo.addons.absar_portal_accounting.models.service import KINDS
    class FakeRequest:
        def __init__(self):self.env=env;self.httprequest=SimpleNamespace(path='/my/employee/accounting')
        def csrf_token(self,*args,**kwargs):return 'design-test'
    vals={'company':company,'companies':company,'roles':{'preparer':True,'approver':False,'monitor':False},
          'kinds':KINDS,'configured':True,'quote_plus':quote_plus,'request':FakeRequest(),'counts':{k:3 for k in KINDS}}
    html=str(env['ir.qweb']._render('absar_portal_accounting.home',vals,minimal_qcontext=True))
    dom=etree.HTML(html)
    assert len(dom.xpath("//a[@class='aca-card']"))==7
    assert dom.xpath("//a[@class='aca-card']/@style")==['--card-order:%s'%i for i in range(7)]
    vals.update(kind='planned',title='Planned Payments',q='',status='',message='',count=1,page=1,rows=[{
        'id':1,'name':'Design QA long document title','partner':'Vendor Ref','date':'2026-10-19','journal':'Bank',
        'amount':12345.5,'currency':'SAR','state':'planned','review':'not_sent','issuer':'Employee Name','version':'qa'}])
    html=str(env['ir.qweb']._render('absar_portal_accounting.listing',vals,minimal_qcontext=True))
    assert 'aca-bulk-bar' in html and 'aca-date-col' in html and '12,345.50' in html
    vals.update(rows=[],configured=False)
    html=str(env['ir.qweb']._render('absar_portal_accounting.listing',vals,minimal_qcontext=True))
    assert 'colspan="9"' in html and 'Configuration → Settings → Employee Portal Accounting' in html
    vals['boot_json']='{}'
    assert 'aca-editor' in str(env['ir.qweb']._render('absar_portal_accounting.detail',vals,minimal_qcontext=True))
    print('PASS: real QWeb cards/stagger values, planned bulk list, stable dates/amount markup, empty selection colspan, new settings help and detail render.',flush=True)
