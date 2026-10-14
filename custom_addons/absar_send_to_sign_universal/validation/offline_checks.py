"""Execute universal code with ORM doubles; no live Odoo claims."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from lxml import etree

ROOT = Path(__file__).parent.parent if Path(__file__).parent.name == 'validation' else Path(__file__).parent / 'absar_send_to_sign_universal'
I = ast.parse((ROOT/'models/integration.py').read_text())
D = ast.parse((ROOT/'models/document.py').read_text())
class UserError(Exception): pass
class AccessError(Exception): pass
class ValidationError(Exception): pass

def function(tree, cls, name):
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    fn = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == name)
    fn.decorator_list=[]
    scope={'_':lambda s:s,'UserError':UserError,'AccessError':AccessError,'ValidationError':ValidationError,
           'Command':N(clear=lambda:(5,0,0),create=lambda vals:(0,0,vals)),
           'sql':N(SQL=lambda value:N(format=lambda *a:value),Identifier=lambda value:value),
           'SPECIALIZED_MODELS':{'purchase.order','account.payment.voucher','construction.contract','construction.measurement','construction.ipc'}}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual module method>','exec'),scope)
    return scope[name]

class Record:
    _name='sale.order'
    _fields={}
    id=7
    def __len__(self):return 1
    def check_access_rights(self,mode): self.checked_rights=mode
    def check_access_rule(self,mode):self.checked_rules=mode
    def __getitem__(self,key):return self.state

class Tests(unittest.TestCase):
    def config(self,sign=True,active=True,states='',field=False):
        return N(ensure_one=lambda:None,active=active,model_id=N(model='sale.order'),
                 env=N(user=N(has_group=lambda g:sign,groups_id=set()),company=N(id=1),companies=N(ids=[1])),
                 state_field_id=field,allowed_states=states,report_id=N(groups_id=set()),
                 _allowed_state_values=lambda:[x.strip() for x in states.split(',') if x.strip()])
    def test_source_requires_sign_access(self):
        with self.assertRaises(AccessError):function(I,'UniversalIntegration','_check_source')(self.config(sign=False),Record())
    def test_inactive_integration_rejected(self):
        with self.assertRaises(UserError):function(I,'UniversalIntegration','_check_source')(self.config(active=False),Record())
    def test_model_mismatch_rejected(self):
        r=Record();r._name='purchase.order'
        with self.assertRaises(UserError):function(I,'UniversalIntegration','_check_source')(self.config(),r)
    def test_multiple_records_rejected(self):
        class Multi(Record):
            def __len__(self):return 2
        with self.assertRaises(UserError):function(I,'UniversalIntegration','_check_source')(self.config(),Multi())
    def test_source_permissions_checked(self):
        r=Record();company=function(I,'UniversalIntegration','_check_source')(self.config(),r)
        self.assertEqual(company.id,1);self.assertEqual(r.checked_rights,'write');self.assertEqual(r.checked_rules,'write')
    def test_wrong_company_rejected(self):
        r=Record();r._fields={'company_id':True};r.company_id=N(id=2)
        with self.assertRaises(AccessError):function(I,'UniversalIntegration','_check_source')(self.config(),r)
    def test_state_guard_rejects_draft(self):
        r=Record();r.state='draft'
        with self.assertRaises(UserError):function(I,'UniversalIntegration','_check_source')(self.config(states='posted',field=N(name='state')),r)
    def test_state_guard_accepts_posted(self):
        r=Record();r.state='posted'
        self.assertEqual(function(I,'UniversalIntegration','_check_source')(self.config(states='posted',field=N(name='state')),r).id,1)
    def test_report_permissions_checked(self):
        c=self.config();c.report_id.groups_id={12}
        with self.assertRaises(AccessError):function(I,'UniversalIntegration','_check_source')(c,Record())
    def test_states_trimmed(self):
        self.assertEqual(function(I,'UniversalIntegration','_allowed_state_values')(N(allowed_states=' sale, done, ')),['sale','done'])
    def test_buttons_with_existing_header(self):
        node=next(n for n in I.body if isinstance(n,ast.FunctionDef) and n.name=='button_arch');scope={'etree':etree};exec(compile(ast.Module(body=[node],type_ignores=[]),'<button>','exec'),scope)
        root=etree.fromstring(scope['button_arch'](42,True).encode());self.assertEqual(root[0].get('expr'),'/form/header');self.assertEqual(root[0][0].get('type'),'action');self.assertEqual(root[0][0].get('name'),'42')
    def test_buttons_without_header(self):
        node=next(n for n in I.body if isinstance(n,ast.FunctionDef) and n.name=='button_arch');scope={'etree':etree};exec(compile(ast.Module(body=[node],type_ignores=[]),'<button>','exec'),scope)
        root=etree.fromstring(scope['button_arch'](42,False).encode());self.assertEqual(root[0].get('position'),'before');self.assertEqual(root[0][0].tag,'header')
    def test_source_business_fields_not_written(self):
        for tree in (I,D):
            calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='write']
            for call in calls:self.assertNotIn(ast.unparse(call.func.value),['source','record','records'])
    def test_bridge_callback_metadata_not_assigned(self):
        text=(ROOT/'models/integration.py').read_text();self.assertNotIn("'absar_source_model':",text);self.assertNotIn("'absar_source_id':",text)
    def test_native_wizard_has_singleton_guard_fix(self):
        for field in ['has_default_template','signers_count']:
            self.assertIn(field,(ROOT/'models/document.py').read_text())
    def test_superseded_preparation_rejected(self):
        obj=N(ensure_one=lambda:None,integration_id=N(id=1),source_id=2,id=3)
        obj.sudo=lambda:N(search=lambda *a,**k:N(id=4))
        with self.assertRaisesRegex(UserError,'superseded'):function(D,'UniversalDocument','_check_latest_preparation')(obj)
    def test_latest_preparation_accepted(self):
        obj=N(ensure_one=lambda:None,integration_id=N(id=1),source_id=2,id=3)
        obj.sudo=lambda:N(search=lambda *a,**k:N(id=3))
        function(D,'UniversalDocument','_check_latest_preparation')(obj)
    def test_config_excludes_specialized_models(self):
        text=(ROOT/'models/integration.py').read_text()
        for model in ['purchase.order','account.payment.voucher','construction.ipc']:self.assertIn(model,text)
    def test_all_placement_columns_extended(self):
        root=etree.parse(str(ROOT/'views/workflow_views.xml'))
        self.assertEqual(len(root.xpath('//attribute[@name="column_invisible"]')),5)
    def existing_flow(self, request_state='sent'):
        source=Record();source._table='sale_order';source.ids=[7];source.invalidate_recordset=lambda:None
        template=N(check_access_rights=lambda mode:None,check_access_rule=lambda mode:None)
        existing=N(with_user=lambda user:existing,_source=lambda:source,
                   action_open_signing=lambda:{'type':'existing'},invalidate_recordset=lambda fields:None,
                   request_id=N(state=request_state) if request_state else False,template_id=template)
        model=N(sudo=lambda:model,search=lambda *a,**k:existing)
        class Env:
            user=N(id=4)
            cr=N(execute=lambda *a:None)
            def __getitem__(self,key):return model
        config=N(ensure_one=lambda:None,id=1,env=Env(),_validate_configuration=lambda:None,
                 _check_source=lambda record:N(id=1))
        return config,source
    def test_repeat_click_reuses_existing_request(self):
        config,source=self.existing_flow()
        self.assertEqual(function(I,'UniversalIntegration','action_send')(config,source),{'type':'existing'})
    def test_new_revision_blocks_pending_request(self):
        config,source=self.existing_flow()
        with self.assertRaisesRegex(UserError,'still active'):
            function(I,'UniversalIntegration','action_send')(config,source,new_revision=True)
    def test_new_revision_rechecks_before_repreparing(self):
        config,source=self.existing_flow('signed')
        def next_phase(record,company):raise RuntimeError('workflow resolution reached')
        config._get_workflow=next_phase
        with self.assertRaisesRegex(RuntimeError,'workflow resolution reached'):
            function(I,'UniversalIntegration','action_send')(config,source,new_revision=True)
    def test_repeat_click_reuses_unsent_template(self):
        config,source=self.existing_flow(None)
        # Only reuses the existing artifact; it does not call native sending again.
        self.assertEqual(function(I,'UniversalIntegration','action_send')(config,source),{'type':'existing'})
    def test_prepared_recipients_and_order_are_frozen(self):
        snapshot=[{'partner_id':10,'role_id':20,'order':1},{'partner_id':11,'role_id':21,'order':2}]
        doc=N(signer_snapshot=snapshot,_validate_snapshot=lambda:None);doc.sudo=lambda:doc
        class Env:
            def __getitem__(self,key):return N(_fields={'mail_sent_order':True})
        wizard=N(env=Env())
        template=N(absar_universal_document_id=doc,absar_workflow_id=N(step_ids=['changed workflow']))
        result=function(D,'SignSendRequest','_absar_signer_commands')(wizard,template)
        self.assertEqual(result,[(5,0,0),(0,0,{'partner_id':10,'role_id':20,'mail_sent_order':1}),
                                 (0,0,{'partner_id':11,'role_id':21,'mail_sent_order':2})])
    def test_snapshot_errors_are_not_silenced(self):
        def invalid():raise UserError('invalid signer')
        doc=N(_validate_snapshot=invalid);doc.sudo=lambda:doc
        with self.assertRaisesRegex(UserError,'invalid signer'):
            function(D,'SignSendRequest','_absar_signer_commands')(N(),N(absar_universal_document_id=doc))
    def test_manifest_and_xml(self):
        manifest=ast.literal_eval((ROOT/'__manifest__.py').read_text())
        for name in manifest['data']:
            self.assertTrue((ROOT/name).is_file())
            if name.endswith('.xml'):etree.parse(str(ROOT/name))
        for p in ROOT.rglob('*.py'):ast.parse(p.read_text())

if __name__=='__main__':unittest.main()
