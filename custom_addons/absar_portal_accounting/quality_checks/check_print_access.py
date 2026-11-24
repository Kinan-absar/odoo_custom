"""Run without Odoo: exercise the actual print route with strict portal ACL fixtures."""
import ast
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).parents[1] / 'controllers' / 'portal.py'
module = ast.parse(source.read_text())
method = next(n for c in module.body if isinstance(c, ast.ClassDef)
              for n in c.body if isinstance(n, ast.FunctionDef) and n.name == 'print_record')
method.decorator_list = []

class Denied(Exception):
    pass

class UserError(Exception):
    pass

class Action:
    _name = 'ir.actions.report'
    def __init__(self, model='account.move', elevated=False):
        self.target_model = model
        self.elevated = elevated
    @property
    def model(self):
        if not self.elevated:
            raise Denied('Portal cannot read Report Action')
        return self.target_model
    def sudo(self):
        events.append('metadata sudo')
        return Action(self.target_model, True)

class Env:
    def ref(self, ref, raise_if_not_found=False):
        assert ref == 'wm_journal_entry_report.account_journal'
        events.append('lookup')
        return action

class Renderer:
    def _render_qweb_pdf(self, ref, res_ids):
        events.append(('render', ref, res_ids))
        return b'%PDF-fixture', 'pdf'

class Service:
    def _company(self, cid):
        assert cid == 1
        return SimpleNamespace(id=1)
    def _record(self, company, kind, rid):
        events.append('authorize')
        if blocked:
            raise Denied('Document outside portal scope')
        return records[kind]
    def _env(self, company):
        return {'ir.actions.report': Renderer()}

move = SimpleNamespace(_name='account.move', ids=[11341], name='BILL/TEST')
records = {'bills': move, 'journals': move,
           'payments': SimpleNamespace(_name='account.payment.voucher', move_id=move)}
request = SimpleNamespace(env=Env(), make_response=lambda pdf, headers: (pdf, headers))
namespace = dict(request=request, UserError=UserError, NotFound=LookupError,
                 content_disposition=lambda value: value, _=lambda value: value)
exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
controller = SimpleNamespace(_service=lambda: Service())
route = namespace['print_record']
action = Action()
blocked = False
for kind, journal in [('bills', '1'), ('payments', '1'), ('journals', None)]:
    events = []
    assert route(controller, kind, 11341, company_id=1, journal_entry=journal)[0].startswith(b'%PDF')
    assert events == ['authorize', 'lookup', 'metadata sudo',
                      ('render', 'wm_journal_entry_report.account_journal', [11341])]
for action in (None, Action('res.partner')):
    events = []
    try:
        route(controller, 'bills', 11341, company_id=1, journal_entry='1')
    except UserError:
        assert not any(isinstance(event, tuple) for event in events)
    else:
        raise AssertionError('Missing/incorrect report must not render')
action = Action()
blocked = True
events = []
try:
    route(controller, 'bills', 11341, company_id=1, journal_entry='1')
except Denied:
    assert events == ['authorize']
else:
    raise AssertionError('Unauthorized bill must not print')
print('PASS: portal JV metadata ACL, bill/voucher/journal targets, missing/wrong report, authorization before elevation.')
