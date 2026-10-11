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
assert manifest['version'] == '18.0.2.0.7'
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
        if key=='_name':return self.model_obj.technical_name
        value=self.model_obj.rows[self.id].get(key,False)
        return Link(value) if key in ['paperformat_id','binding_model_id'] else value
    def exists(self):return RS(self.model_obj,[i for i in self.ids if i in self.model_obj.rows])
    def sudo(self):return self
    def write(self, values):
        for i in self.ids:self.model_obj.rows[i].update(values)
    def mapped(self, field):return [self.model_obj.rows[i][field] for i in self.ids]
    def unlink(self):
        for i in self.ids:self.model_obj.rows.pop(i,None)
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
    technical_name='ir.actions.report'
    def __init__(self):self.rows={}
    def create(self, values):
        i=max(self.rows,default=0)+1;self.rows[i]=dict(values);return self.browse(i)
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
class Metadata(ActionModel):
    technical_name='ir.model.data'
    def __init__(self,env):super().__init__();self.env=env
    def create(self,values):
        row=super().create(values)
        self.env.refs[values['module']+'.'+values['name']]=values['res_id']
        return row
class Params:
    def __init__(self):self.values={}
    def sudo(self):return self
    def get_param(self,k,default=False):return self.values.get(k,default)
    def set_param(self,k,v):self.values[k]=v
class Env:
    su=True
    def __init__(self):self.actions=ActionModel();self.params=Params();self.refs={};self.metadata=Metadata(self)
    def __getitem__(self,k):
        if k=='ir.actions.report':return self.actions
        if k=='ir.model.data':return self.metadata
        if k=='ir.config_parameter':return self.params
        if k=='ir.model':return types.SimpleNamespace(_get=lambda name:Link({'account.move':1,'purchase.order':2,'sale.order':3}[name]))
        raise KeyError(k)
    def ref(self,k,raise_if_not_found=True):
        if k.endswith('_paperformat'):return Link(10 if 'business' in k else 11)
        if k in self.refs:return self.actions.browse(self.refs[k]).exists()
        if raise_if_not_found:raise KeyError(k)
        return False
odoo=types.ModuleType('odoo');odoo.api=types.SimpleNamespace(model=lambda f:f);odoo.models=types.SimpleNamespace(AbstractModel=object,Model=object);odoo.fields=types.SimpleNamespace(Datetime=types.SimpleNamespace(now=lambda:'TEST'))
errors=types.ModuleType('odoo.exceptions');errors.AccessError=type('AccessError',(Exception,),{})
sys.modules['odoo']=odoo;sys.modules['odoo.exceptions']=errors
pkg=types.ModuleType('absar_test');pkg.__path__=[str(ROOT/'models')];sys.modules['absar_test']=pkg
spec=importlib.util.spec_from_file_location('absar_test.report_setup',ROOT/'models/report_setup.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
from absar_test.cleanup_plan import plan_cleanup
def simulated_cleanup(env,config,keep,duplicate_action_ids=()):
    candidates={('ir.actions.report',i) for i in duplicate_action_ids}
    owners={}
    for xmlid,i in env.refs.items():owners.setdefault(('ir.actions.report',i),set()).add(xmlid.split('.')[0])
    removable,_=plan_cleanup(candidates,owners,{('ir.actions.report',i) for i in keep.ids},[])
    for _,i in removable:
        env.actions.browse(i).unlink()
        env.metadata.search([('res_id','=',i)]).unlink()
        env.refs={k:v for k,v in env.refs.items() if v!=i}
    return {}
module.cleanup_reports=simulated_cleanup
config=json.loads((ROOT/'data/integration.json').read_text())
def scenario(existing, upgrade=False):
    env=Env()
    rich_po = "'%s - %s - %s - %s' % (object.name, object.partner_id.name, object.project_id.name, object.material_request_id.name)"
    for i,item in enumerate(config['reports'],1):
        values={'name':item['name'],'model':item['model'],'report_name':item['legacy_report'],
                'report_file':item['legacy_report'],'paperformat_id':99,'binding_model_id':1,
                'print_report_name':rich_po if item['alias']=='purchase_report' else "'Original filename - %s' % object.name"}
        if existing:
            env.actions.rows[i+100]=values
            if item.get('xmlid'):env.refs[item['xmlid']]=i+100
        if upgrade:
            env.actions.rows[i]=dict(values,report_name='absar_report_suite.'+item['alias'],print_report_name='object.name')
            env.metadata.create({'module':'absar_report_suite','name':item['alias'],
                                 'model':'ir.actions.report','res_id':i,'noupdate':False})
            env.params.set_param('absar_report_suite.target.'+item['alias'],str(i+100))
    env.actions.rows[999]={'name':'Unrelated','model':'account.move','report_name':'other.report','binding_model_id':1}
    untouched=dict(env.actions.rows[999])
    setup=module.AbsarReportSetup();setup.env=env
    setup.apply();first=json.loads(env.params.get_param('absar_report_suite.original_report_actions'))
    state={i:dict(v) for i,v in env.actions.rows.items()}
    setup.apply()
    assert state==env.actions.rows
    assert first==json.loads(env.params.get_param('absar_report_suite.original_report_actions'))
    assert env.actions.rows[999]==untouched
    assert len(env.actions.rows)==9, env.actions.rows
    for item in config['reports']:
        target=int(env.params.get_param('absar_report_suite.target.'+item['alias']))
        row=env.actions.rows[target]
        assert row['report_name']==item['report_name']
        assert row['binding_model_id']
        if existing:assert row['print_report_name']==('object._absar_report_filename()' if item['alias']=='purchase_report' else "'Original filename - %s' % object.name")
    purchase_id=int(env.params.get_param('absar_report_suite.target.purchase_report'))
    assert env.actions.rows[purchase_id]['report_name']=='purchase.report_purchaseorder'
    if not existing:assert env.actions.rows[purchase_id]['print_report_name']=='object._absar_report_filename()'
    if upgrade:assert all(i not in env.actions.rows for i in range(1,9))
    checked('Actual setup: fresh='+str(not existing)+'; duplicate upgrade='+str(upgrade)+'; repeat setup and filenames')
scenario(False);scenario(True);scenario(True,True)
# Prove an older rich expression cannot reintroduce a prefix or the wrong field order.
env=Env();env.actions.rows[42]={'name':'Purchase Order','model':'purchase.order','report_name':'absar_report_suite.purchase','print_report_name':'object.name'}
env.refs['purchase.action_report_purchase_order']=42
env.params.set_param('absar_report_suite.original_report_actions',json.dumps({'42':{'print_report_name':"'%s - %s - %s - %s' % (object.name, object.partner_id.name, object.project_id.name, object.material_request_id.name)"}}))
setup=module.AbsarReportSetup();setup.env=env;setup.apply()
assert env.actions.rows[42]['print_report_name']=='object._absar_report_filename()'
bridge=E.parse(str(ROOT/'reports/compatibility.xml'))
assert bridge.find('template').get('inherit_id')=='purchase.report_purchaseorder'
assert bridge.xpath('//t[@t-call="absar_report_suite.purchase"]')
assert not any(r.get('model')=='ir.actions.report' for r in records.values())
checked('PO filename policy replaces older saved expressions; legacy PO QWeb bridge and no declarative duplicate action creation')
spec=importlib.util.spec_from_file_location('absar_test.purchase_order',ROOT/'models/purchase_order.py')
po_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(po_module)
class DummyPurchase(po_module.PurchaseOrder):
    def __init__(self, optional=True, state='purchase'):
        self.name='P00123';self.partner_id=types.SimpleNamespace(name='Supplier Test');self.state=state
        self._fields={'project_id','material_request_id'} if optional else set()
        self.links={'project_id':types.SimpleNamespace(name='Project Test'),
                    'material_request_id':types.SimpleNamespace(name='MR/0123')}
    def ensure_one(self):pass
    def __getitem__(self,name):return self.links[name]
assert DummyPurchase()._absar_report_filename()=='P00123 - Supplier Test - MR/0123 - Project Test'
assert DummyPurchase(state='draft')._absar_report_filename()=='P00123 - Supplier Test - MR/0123 - Project Test'
assert DummyPurchase(optional=False)._absar_report_filename()=='P00123 - Supplier Test'
example=DummyPurchase();example.name='PO 238';example.partner_id.name='مؤسسة نورة الدوسري التجارية'
example.links['material_request_id'].name='MR-00708';example.links['project_id'].name='MEP Jussur Emdad HR'
assert example._absar_report_filename()=='PO 238 - مؤسسة نورة الدوسري التجارية - MR-00708 - MEP Jussur Emdad HR'
example.revision=2
assert example._absar_report_filename().endswith('_R2')
checked('Actual PO filename helper: exact supplied Arabic title, MR/project order, no prefix in draft/confirmed, revisions and absent optional fields')
assert 'state' not in module._FIELDS
assert 'unlink(' not in (ROOT/'models/report_setup.py').read_text()
checked('Report rebinding does not force module state')
from absar_test.cleanup_plan import plan_cleanup
a=('ir.ui.view',1);b=('ir.ui.view',2);c=('ir.actions.report',3);system=('ir.ui.view',4);retained=('ir.ui.view',5)
remove,reasons=plan_cleanup({a,b,c,system},{a:{'studio_customization'},b:set(),c:{'studio_customization'},system:{'account'}},set(),[(a,b),(c,a)])
assert remove=={a,b,c} and system in reasons
remove,reasons=plan_cleanup({a,b,c}, {},set(),[(retained,a),(a,b),(c,a)])
assert remove=={c} and a in reasons and b in reasons
remove,reasons=plan_cleanup({a,b}, {},{a},[(a,b),(b,a)])
assert not remove
remove,reasons=plan_cleanup({a,b}, {},set(),[(a,b),(b,a)])
assert remove=={a,b}
remove,reasons=plan_cleanup({a,c}, {},set(),[(None,c),(c,a)])
assert not remove
checked('Cleanup graph: system ownership, retained inheritance, cycles and external references')
assert all(v['key'] not in views for v in config['retired_views'])
assert set(config['retired_templates']).isdisjoint(views)
checked('Cleanup allowlist excludes the rebuilt report templates')
print(json.dumps({'result':'PASS','offline_checks':checks,'odoo_installation_tested':False,'live_pdf_rendering_tested':False},indent=2))
