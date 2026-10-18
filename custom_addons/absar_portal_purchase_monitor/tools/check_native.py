"""Native scope and bootstrap regression checks; no Odoo runtime required."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace as NS
from lxml import etree
try:
    from markupsafe import Markup
except ImportError:
    class Markup(str):
        """String marker fixture; the Odoo dependency supplies the real class."""
        pass

ROOT = Path(__file__).resolve().parents[1]
checks = 0

def check(value):
    global checks
    assert value
    checks += 1

rules = etree.parse(str(ROOT/'security/native_rules.xml'))
class User:
    def __init__(self, roles=(), share=True):
        self.id = 7
        self.share = share
        self.roles = set(roles)
        self.partner_id = NS(commercial_partner_id=NS(id=22))
        self.absar_purchase_project_ids = NS(ids=[91])
    def has_group(self, name):
        return name.rsplit('group_portal_purchase_', 1)[-1] in self.roles

def domain(key, user):
    node = rules.xpath('//record[@id="%s"]/field[@name="domain_force"]' % key)[0]
    return eval(node.text, {'__builtins__': {}}, {'user': user, 'company_ids': [1]})

def match(domain, record):
    def leaf(term):
        field, op, rhs = term
        lhs = term[0] if isinstance(field, int) else record.get(field)
        if lhs is False and type(rhs) is int and rhs == 0:
            return False
        return {'=': lambda: lhs == rhs, '!=': lambda: lhs != rhs,
                'in': lambda: lhs in rhs, '>': lambda: lhs > rhs}[op]()
    def part(pos):
        item = domain[pos]
        if item == '|':
            a, pos = part(pos+1); b, pos = part(pos)
            return a or b, pos
        if item == '&':
            a, pos = part(pos+1); b, pos = part(pos)
            return a and b, pos
        if item == '!':
            a, pos = part(pos+1); return not a, pos
        return leaf(item), pos+1
    result, pos = True, 0
    while pos < len(domain):
        current, pos = part(pos); result = result and current
    return result

for role in ('preparer', 'approver', 'monitor', 'confirmer'):
    actor = User(('native', role))
    for company in (1, 2):
        for owner in (False, 7, 8):
            for state in ('draft', 'sent', 'purchase', 'done'):
                for review in ('draft', 'submitted', 'approved', 'returned'):
                    record = {'company_id':company, 'absar_portal_preparer_id':owner,
                              'state':state, 'absar_portal_review_state':review}
                    expected = company == 1 and (
                        (role=='preparer' and owner==7) or
                        (role=='approver' and bool(owner) and review in ('submitted','approved','returned')) or
                        (role=='confirmer' and bool(owner) and review=='approved') or
                        (role=='monitor' and state in ('purchase','done')))
                    check(match(domain('native_scope_order',actor),record)==expected)
                    line = {'order_id.'+key:value for key,value in record.items()}
                    check(match(domain('native_scope_line',actor),line)==expected)
                    editable = company==1 and owner==7 and state in ('draft','sent') and review in ('draft','returned')
                    check(match(domain('native_edit_order',actor),record)==editable)
# Native globals leave pre-existing non-opted-in and internal permissions untouched.
check(domain('native_scope_order',User((),True)) == [(1,'=',1)])
check(domain('native_scope_order',User(('native','preparer'),False)) == [(1,'=',1)])
# Execute the actual JSON bootstrap encoder, including an HTML/script terminator.
tree=ast.parse((ROOT/'controllers/native_workspace.py').read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='script_json')
ns={'json':json,'Markup':Markup}; exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'bootstrap','exec'),ns)
value={'test':'</script><img onerror="alert(1)"> & \u2028'}
encoded=ns['script_json'](value)
check(isinstance(encoded,Markup));check('<' not in encoded);check('&' not in encoded);check(json.loads(encoded)==value)
# Every domain can be evaluated for an eligible employee, even if not queried here.
for node in rules.xpath('//record/field[@name="domain_force"]'):
    check(isinstance(eval(node.text,{'__builtins__':{}},{'user':User(('native','preparer')),'company_ids':[1]}),list))
# CRUD access stays behind the newly introduced explicit opt-in group.
import csv
with (ROOT/'security/ir.model.access.csv').open() as f:
    for row in csv.DictReader(f):
        if row['model_id:id'] != 'model_absar_portal_purchase_return':
            check(row['group_id:id']=='group_portal_purchase_native')
check('base.group_user' not in ''.join(etree.parse(str(ROOT/'security/groups.xml')).xpath('//field[@name="implied_ids"]/@eval')))
print(f'{checks} native scope/bootstrap/opt-in ACL checks passed; Odoo ORM/browser integration not exercised.')
