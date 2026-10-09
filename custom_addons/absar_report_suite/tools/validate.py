"""Offline package checks and action-setup simulation; NOT an Odoo install test."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
import types
from lxml import etree as E
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
manifest = ast.literal_eval((ROOT / '__manifest__.py').read_text())
checks = []
def checked(name):
    checks.append(name)

for path in ROOT.rglob('*.py'):
    ast.parse(path.read_text())
checked('Python syntax')
assert manifest['version'] == '18.0.2.0.0'
assert not {'wm_journal_entry_report', 'sale_pdf_quote_builder', 'studio_customization'} & set(manifest['depends'])
records = {}
for filename in manifest['data']:
    tree = E.parse(str(ROOT / filename))
    assert tree.getroot().tag == 'odoo'
    for record in tree.findall('record'):
        assert record.get('id') not in records
        records[record.get('id')] = record
checked('Manifest data order and unique XML record identities')
views = {r.find('field[@name="key"]').text: r.find('field[@name="arch"]')[0]
         for r in records.values() if r.get('model') == 'ir.ui.view'}
external_calls = {'web.html_container', 'web.address_layout', 'account.document_tax_totals',
                  'account.document_tax_totals_company_currency_template'}
for key, tree in views.items():
    assert tree.get('t-name') == key
    for call in tree.xpath('.//@t-call'):
        assert call in views or call in external_calls, (key, call)
    for el in tree.iter():
        for attr, expression in el.attrib.items():
            if attr in {'t-if','t-elif','t-value','t-out','t-esc','t-foreach','t-options'} or attr.startswith('t-att-'):
                ast.parse(expression, mode='eval')
    assert '/web/image/' not in E.tostring(tree).decode()
checked('QWeb calls, expression syntax and portable assets')
assert 'purchase.report_purchaseorder_document' not in E.tostring(views['absar_report_suite.purchase']).decode()
assert 'Printed by:' in E.tostring(views['absar_report_suite.journal_layout']).decode()
assert 'Footer Image' not in E.tostring(views['absar_report_suite.journal_layout']).decode()
assert 'border:0!important' in E.tostring(views['absar_report_suite.report_styles']).decode()
for asset in ['letterhead', 'footer', 'stamp']:
    with Image.open(ROOT / 'static/img' / (asset + '.png')) as im: im.verify()
checked('Journal footer, purchase routing and three image files')

# Exercise the actual action setup code against an in-memory ORM substitute.
class Link:
    def __init__(self, id): self.id = id
    def __bool__(self): return bool(self.id)
class RS:
    def __init__(self, model, ids=()): self.model_obj=model; self.ids=list(dict.fromkeys(ids))
    def __iter__(self): return (RS(self.model_obj,[i]) for i in self.ids)
    def __len__(self): return len(self.ids)
    def __bool__(self): return bool(self.ids)
    def __contains__(self, other): return all(i in self.ids for i in other.ids)
    def __eq__(self, other): return isinstance(other,RS) and self.ids==other.ids and self.model_obj is other.model_obj
    def __or__(self, other): return RS(self.model_obj,self.ids+other.ids)
    def __sub__(self, other): return RS(self.model_obj,[i for i in self.ids if i not in other.ids])
    def __getitem__(self, key):
        if isinstance(key,slice): return RS(self.model_obj,self.ids[key])
        return getattr(self,key)
    def __getattr__(self, key):
        if key=='id':return self.ids[0] if self.ids else False
        if key=='_name':return 'ir.actions.report'
        value=self.model_obj.rows[self.id].get(key,False)
        return Link(value) if key in ['paperformat_id','binding_model_id'] else value
    def exists(self):return RS(self.model_obj,[i for i in self.ids if i in self.model_obj.rows])
    def sudo(self):return self
    def write(self, values):
        for i in self.ids:self.model_obj.rows[i].update(values)
    def read(self, fields):
        result=[]
        for i in self.ids:
            row={'id':i}
            for field in fields:
                val=self.model_obj.rows[i].get(field,False)
                row[field]=[val,'Relation'] if field in ['binding_model_id','paperformat_id'] and val else val
            result.append(row)
        return result
class ActionModel:
    def __init__(self):self.rows={}
    def sudo(self):return self
    def browse(self, ids=()):return RS(self,[ids] if isinstance(ids,int) else ids)
    def search(self,domain,order=None):
        def match(i,row):
            it=iter(domain)
            def consume(token):
                if token in ['|','&']:
                    a=consume(next(it));b=consume(next(it));return a or b if token=='|' else a and b
                key,op,val=token;actual=i if key=='id' else row.get(key,False)
                if op=='=':return actual==val
                if op=='in':return actual in val
                if op=='not in':return actual not in val
                raise AssertionError(op)
            parts=[]
            for token in it:parts.append(consume(token))
            return all(parts)
        return self.browse([i for i,row in self.rows.items() if match(i,row)])
class Params:
    def __init__(self):self.values={}
    def sudo(self):return self
    def get_param(self,k,default=False):return self.values.get(k,default)
    def set_param(self,k,v):self.values[k]=v
class Env:
    su=True
    def __init__(self):self.actions=ActionModel();self.params=Params();self.refs={}
    def __getitem__(self,k):
        if k=='ir.actions.report':return self.actions
        if k=='ir.config_parameter':return self.params
        if k=='ir.model':return types.SimpleNamespace(_get=lambda name:Link({'account.move':1,'purchase.order':2,'sale.order':3}[name]))
        raise KeyError(k)
    def ref(self,k,raise_if_not_found=True):
        if k in self.refs:return self.actions.browse(self.refs[k])
        if raise_if_not_found:raise KeyError(k)
        return False
odoo=types.ModuleType('odoo');odoo.api=types.SimpleNamespace(model=lambda f:f);odoo.models=types.SimpleNamespace(AbstractModel=object)
errors=types.ModuleType('odoo.exceptions');errors.AccessError=type('AccessError',(Exception,),{})
sys.modules['odoo']=odoo;sys.modules['odoo.exceptions']=errors
spec=importlib.util.spec_from_file_location('setup_under_test',ROOT/'models/report_setup.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
config=json.loads((ROOT/'data/integration.json').read_text())
def scenario(existing, extras=False):
    env=Env()
    for i,item in enumerate(config['reports'],1):
        canonical=records[item['alias']]
        values={f.get('name'): f.text for f in canonical.findall('field') if f.get('ref') is None and f.get('eval') is None}
        values.update(paperformat_id=10 if item['paper']=='business' else 11,binding_model_id={'account.move':1,'purchase.order':2,'sale.order':3}[item['model']],attachment_use=False)
        env.actions.rows[i]=values;env.refs['absar_report_suite.'+item['alias']]=i
        if existing:
            legacy=dict(values,report_name=item['legacy_report'],report_file=item['legacy_report'],paperformat_id=99)
            env.actions.rows[i+100]=legacy
            if item.get('xmlid'):env.refs[item['xmlid']]=i+100
    if extras:
        for j,(xmlid,alias) in enumerate({'account.account_invoices':'invoice_payment_report','account.account_invoices_without_payment':'invoice_report','sale.action_report_saleorder':'quotation_report','sale.action_report_pro_forma_invoice':'proforma_report'}.items(),201):
            item=next(r for r in config['reports'] if r['alias']==alias)
            env.actions.rows[j]={'name':'Standard '+alias,'model':item['model'],'report_name':'standard.'+alias,'binding_model_id':1,'paperformat_id':98}
            env.refs[xmlid]=j
        item=next(r for r in config['reports'] if r['alias']=='purchase_report')
        env.actions.rows[300]={'name':item['name'],'model':item['model'],'report_name':item['legacy_report'],'binding_model_id':2,'paperformat_id':97}
    # Unrelated report must survive byte-for-byte.
    env.actions.rows[999]={'name':'Unrelated','model':'account.move','report_name':'other.report','binding_model_id':1}
    untouched=dict(env.actions.rows[999])
    setup=module.AbsarReportSetup();setup.env=env
    setup.apply();first=json.loads(env.params.get_param('absar_report_suite.original_report_actions'))
    state={i:dict(v) for i,v in env.actions.rows.items()}
    setup.apply()
    assert state==env.actions.rows
    assert first==json.loads(env.params.get_param('absar_report_suite.original_report_actions'))
    assert env.actions.rows[999]==untouched
    for item in config['reports']:
        target=int(env.params.get_param('absar_report_suite.target.'+item['alias']))
        assert env.actions.rows[target]['report_name']==item['report_name']
        assert env.actions.rows[target]['binding_model_id']
    if existing:
        assert len(first)==(13 if extras else 8)
        assert all(first[str(i+100)]['paperformat_id']==99 for i in range(1,9))
    if extras:
        assert not env.actions.rows[300]['binding_model_id']
        for i in range(201,205):
            assert env.actions.rows[i]['report_name'].startswith('absar_report_suite.')
    checked('Setup, repeat update, retained actions and unrelated records: '+str(existing)+'; duplicates and standard buttons: '+str(extras))
scenario(False);scenario(True);scenario(True,True)
assert 'state' not in module._FIELDS
assert 'unlink(' not in (ROOT/'models/report_setup.py').read_text()
checked('Installer does not force module state or delete report records')
print(json.dumps({'result':'PASS','offline_checks':checks,'odoo_installation_tested':False,'live_pdf_rendering_tested':False},indent=2))
