"""Regression checks for Odoo view variations, without requiring an Odoo server."""
import importlib.util
from pathlib import Path
from lxml import etree as E

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_view', ROOT/'models/native_view.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
checks = 0

def check(value):
    global checks
    assert value
    checks += 1

for count in (0, 1, 2, 3, 4, 6):
    source = E.Element('form')
    for i in range(count):
        group = E.SubElement(source, 'group' if i % 2 else 'span', groups='uom.group_uom')
        E.SubElement(group, 'field', name='uom_%s' % i)
    E.SubElement(source, 'field', name='hidden_uom', groups='!uom.group_uom')
    lines = E.SubElement(E.SubElement(source, 'field', name='order_line'), 'list')
    E.SubElement(lines, 'field', name='analytic_distribution', groups='analytic.group_analytic_accounting')
    E.SubElement(source, 'field', name='company_id', groups='base.group_multi_company')
    E.SubElement(source, 'button', name='print_quotation', groups='base.group_user')
    E.SubElement(source, 'button', name='button_approve', groups='purchase.group_purchase_manager')
    before = E.tostring(source)
    result = module.prepare_native_arch(source, purchase=True)
    check(E.tostring(source) == before)
    check(len(result.xpath('.//*[@groups="uom.group_uom,%s"]' % module.NATIVE_GROUP)) == count)
    check(result.xpath('.//field[@name="hidden_uom"]')[0].get('groups') == '!uom.group_uom,!' + module.NATIVE_GROUP)
    check(module.NATIVE_GROUP in result.xpath('.//field[@name="analytic_distribution"]')[0].get('groups'))
    check(module.NATIVE_GROUP in result.xpath('.//field[@name="company_id"]')[0].get('groups'))
    check(module.NATIVE_GROUP in result.xpath('.//button[@name="print_quotation"]')[0].get('groups'))
    check(result.xpath('.//button[@name="button_approve"]')[0].get('groups') == 'purchase.group_purchase_manager')
    check(E.tostring(module.prepare_native_arch(result, purchase=True)) == E.tostring(result))
    product = module.prepare_native_arch(source)
    check(product.xpath('.//button[@name="print_quotation"]')[0].get('groups') == 'base.group_user')
# The install-time inheritance records no longer depend on any optional control/group count.
tree = E.parse(str(ROOT/'views/native_presentation.xml'))
for name in ('product_form_native_presentation', 'purchase_form_native_presentation'):
    nodes = tree.xpath('//record[@id="%s"]/field[@name="arch"]/xpath' % name)
    check(len(nodes) == 1 and nodes[0].get('expr') == '//form')
    check(len(E.fromstring(b'<form><sheet/></form>').xpath(nodes[0].get('expr'))) == 1)
print(f'{checks} native view compatibility regression checks passed.')
