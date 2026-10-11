import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS
from lxml import etree
r=Path(__file__).resolve().parents[1]
for p in r.rglob('*.py'):ast.parse(p.read_text())
manifest=ast.literal_eval((r/'__manifest__.py').read_text())
assert manifest['version']=='18.0.1.0.16'
for filename in manifest['data']:
 if filename.endswith('.xml'):etree.parse(str(r/filename))
spec=importlib.util.spec_from_file_location('document_names',r/'tools/document_names.py')
names=importlib.util.module_from_spec(spec);spec.loader.exec_module(names)
filename='PO 238 - مؤسسة نورة الدوسري التجارية - MR-00708 - MEP Jussur Emdad HR'
assert names.signing_title('purchase.order','PO',filename)==filename
assert names.signing_title('account.move','PV','PV001')=='PV - PV001'
assert names.signing_title('construction.contract','Contract','C001')=='Contract - C001'
# Execute the actual upgrade method with isolated record fixtures.
tree=ast.parse((r/'models/sign_workflow.py').read_text())
method=next(n for c in tree.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='remove_duplicate_po_title_prefixes')
method.decorator_list=[]
scope={'_':lambda s:s,'AccessError':RuntimeError}
exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),'upgrade_method','exec'),scope)
class Record(NS):
 def write(self,values):self.__dict__.update(values)
 def exists(self):return self
class Model:
 def __init__(self,rows=()):self.rows=list(rows)
 def sudo(self):return self
 def browse(self,i):return next(r for r in self.rows if r.id==i)
 def search(self,domain):
  rows=self.rows
  for field,op,value in domain:
   if op=='=':rows=[r for r in rows if getattr(r,field)==value]
   elif op=='=like':rows=[r for r in rows if getattr(r,field).startswith(value[:-1])]
  return rows
class Env(dict):su=True
po=Record(id=238,name='PO 238')
old='PO - '+filename
unsigned=Record(id=1,absar_source_model='purchase.order',absar_source_id=238,name=old,attachment_id=Record(name=old+'.pdf'))
signed=Record(id=2,absar_source_model='purchase.order',absar_source_id=238,name=old,attachment_id=Record(name=old+'.pdf'))
unrelated=Record(id=3,absar_source_model='purchase.order',absar_source_id=238,name='PO - Custom Title',attachment_id=Record(name='Custom.pdf'))
active=Record(template_id=1,state='sent',reference=old)
completed=Record(template_id=2,state='signed',reference=old)
env=Env({'purchase.order':Model([po]),'sign.template':Model([unsigned,signed,unrelated]),'sign.request':Model([active,completed])})
method=scope['remove_duplicate_po_title_prefixes'];method(NS(env=env))
assert unsigned.name==filename and unsigned.attachment_id.name==filename+'.pdf' and active.reference==filename
assert signed.name==old and completed.reference==old
assert unrelated.name=='PO - Custom Title'
method(NS(env=env))
assert unsigned.name==filename
method(NS(env=Env()))
print(json.dumps({'result':'PASS','checks':['Python/XML syntax','PO title without extra prefix','Other document titles unchanged','Unsigned template/attachment/request renamed','Signed and unrelated titles preserved','Repeat upgrade','Core without purchase installed'],'live_odoo_tested':False},indent=2))
