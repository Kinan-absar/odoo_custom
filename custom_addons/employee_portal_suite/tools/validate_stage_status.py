"""Offline regression checks for actual status compute methods and inherited views."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace as NS
from lxml import etree as E
ROOT=Path(__file__).resolve().parents[1]
for path in ROOT.rglob('*.py'):ast.parse(path.read_text())
manifest=ast.literal_eval((ROOT/'__manifest__.py').read_text())
assert manifest['version']=='18.0.1.20.92'
for name in manifest['data']:
    if name.endswith('.xml'):E.parse(str(ROOT/name))
def method(filename,name):
    tree=ast.parse((ROOT/filename).read_text())
    fn=next(n for c in tree.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and n.name==name)
    dependencies=[]
    for decorator in fn.decorator_list:
        if isinstance(decorator,ast.Call):dependencies.extend(a.value for a in decorator.args if isinstance(a,ast.Constant))
    fn.decorator_list=[]
    scope={'_':lambda s:s}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),filename,'exec'),scope)
    return scope[name],dependencies
compute,deps=method('models/workflow_v2.py','_compute_approval_status_label')
material,mr_deps=method('models/material_request.py','_compute_display_state')
assert {'state','current_approval_line_id.name','approval_line_ids.state','approval_line_ids.name'} <= set(deps)
assert 'approval_status_label' in mr_deps
class Lines(list):
    @property
    def name(self):return self[0].name if self else False
    def __getitem__(self,key):
        value=super().__getitem__(key)
        return Lines(value) if isinstance(key,slice) else value
    def mapped(self,name):return [getattr(r,name) for r in self]
    def filtered(self,predicate):return Lines([r for r in self if predicate(r)])
class Records(list):
    env=None
    labels={'draft':'Draft','workflow':'Workflow Approval','purchase':'Purchase Representative','approved':'Approved','rejected':'Rejected','returned':'Returned for Correction'}
    _fields={'state':NS(selection=list(labels.items()),_description_selection=lambda env:list(Records.labels.items()))}
pending=NS(state='pending',name='Purchase Representative',sequence=10)
rec=NS(state='workflow',current_approval_line_id=pending,approval_line_ids=Lines([pending]),needs_clarification=False,clarification_stage=False)
rs=Records([rec]);compute(rs);material(rs)
assert rec.display_state=='Purchase Representative'
# Advance the actual pending step; labels must follow the new stage and custom names.
for stage in ['Store Manager','Project Manager','Projects Director','CEO','Project Finance Review']:
    previous = rec.approval_status_color
    line=NS(state='pending',name=stage,sequence=10 + len(rec.approval_line_ids)*10)
    rec.approval_line_ids.append(line);rec.current_approval_line_id=line;compute(rs);material(rs)
    assert rec.approval_status_color != previous
    assert rec.approval_status_label==stage and rec.display_state==stage
rec.state='returned';rec.current_approval_line_id=False;rec.approval_line_ids=Lines([NS(state='returned',name='Store Manager')]);compute(rs);material(rs)
assert rec.display_state=='Returned for Correction — Store Manager'
for state,label in [('approved','Approved'),('rejected','Rejected'),('draft','Draft'),('purchase','Purchase Representative')]:
    rec.state=state;compute(rs);material(rs);assert rec.display_state==label
    assert rec.approval_status_color == {'approved':14,'rejected':15,'draft':0,'purchase':1}[state]
rec.needs_clarification=True;rec.clarification_stage='purchase';material(rs)
assert rec.display_state=='🚩 Clarification — Purchase Representative'
rec.state='workflow';rec.needs_clarification=False;compute(rs);material(rs)
assert rec.display_state=='Workflow Approval' # safe fallback for inconsistent records
# The palette is bounded and remains deterministic with more than twelve stages.
rec.state='workflow';rec.approval_line_ids=Lines([NS(sequence=i*10,name=str(i),state='waiting') for i in range(15)])
seen=[]
for line in rec.approval_line_ids:
    rec.current_approval_line_id=line;compute(rs);seen.append(rec.approval_status_color)
assert len(set(seen[:12])) == 12 and seen[12:] == seen[:3]
# Validate each XPath against the actual parent architecture and apply the changes.
parents={}
for filename in ['employee_request_views.xml','material_request_views.xml']:
    for record in E.parse(str(ROOT/'views'/filename)).xpath('//record[@model="ir.ui.view"]'):
        arch=record.find('field[@name="arch"]')
        if arch is not None and len(arch):parents[record.get('id')]=E.fromstring(E.tostring(arch[0]))
for record in E.parse(str(ROOT/'views/workflow_stage_status_views.xml')).xpath('//record'):
    parent=parents[record.find('field[@name="inherit_id"]').get('ref').split('.')[-1]]
    for xpath in record.findall('field[@name="arch"]/xpath'):
        matches=parent.xpath(xpath.get('expr'));assert matches, xpath.get('expr')
        for target in matches:
            if xpath.get('position')=='replace':
                owner=target.getparent();idx=owner.index(target);owner.remove(target)
                for node in xpath:owner.insert(idx,E.fromstring(E.tostring(node)));idx+=1
            elif xpath.get('position')=='attributes':
                for attr in xpath:target.set(attr.get('name'),attr.text)
            elif xpath.get('position')=='after':
                owner=target.getparent();idx=owner.index(target)+1
                for node in xpath:owner.insert(idx,E.fromstring(E.tostring(node)));idx+=1
assert parents['view_employee_request_list'].xpath('.//field[@name="approval_status_label"]')
for key in ['view_employee_request_form','view_material_request_form']:
    assert parents[key].xpath('.//field[@name="approval_status_label"]')
    assert parents[key].xpath('.//button[@name="action_workflow_approve"]')
print(json.dumps({'result':'PASS','checks':['Python and manifest XML syntax','Pending step advances and arbitrary custom stage names','Returned stage and legacy/completed statuses','MR clarification badge preserved','Computed field dependency invalidation','Inherited view XPath targets and resulting status fields'],'live_odoo_tested':False},indent=2))
