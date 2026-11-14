"""Data-only catalog; scenario labels also serve as the recording shot list."""

EMPLOYEE_STEPS = [('manager', 'Direct Manager'), ('hr', 'HR'),
                  ('finance', 'Finance'), ('ceo', 'CEO')]
MATERIAL_STEPS = [('purchase', 'Purchase Representative'), ('store', 'Store Manager'),
                 ('project_manager', 'Project Manager'), ('director', 'Projects Director'), ('ceo', 'CEO')]

EMPLOYEE_CASES = [
    dict(label='Leave request — draft', kind='leave', stage='draft'),
    dict(label='Annual leave — manager approval', kind='leave', stage=0),
    dict(label='Salary certificate — HR approval', kind='letter', stage=1),
    dict(label='Salary advance — finance approval', kind='advance', stage=2),
    dict(label='Housing allowance — CEO approval', kind='housing', stage=3),
    dict(label='Annual leave — fully approved', kind='leave', stage='approved'),
    dict(label='Salary advance — returned for correction', kind='advance', stage=2, outcome='returned'),
    dict(label='Training request — rejected', kind='training', stage=1, outcome='rejected'),
    dict(label='Business travel — manager approval', kind='travel', stage=0),
    dict(label='Medical reimbursement — finance approval', kind='medical', stage=2),
    dict(label='Bank account change — HR approval', kind='bank', stage=1),
    dict(label='Equipment request — CEO approval', kind='asset', stage=3),
    dict(label='Transfer request — returned by HR', kind='transfer', stage=1, outcome='returned'),
    dict(label='Vacation settlement — approved', kind='vacation_settlement', stage='approved'),
    dict(label='Employment letter — approved with override', kind='letter', stage='approved', override=True),
    dict(label='Clearance request — overdue at HR', kind='exit', stage=1, overdue=True),
]

MATERIAL_CASES = [
    dict(label='Site consumables — draft', stage='draft', quotes=0),
    dict(label='Concrete materials — purchase approval', stage=0, quotes=0),
    dict(label='Safety equipment — store approval', stage=1, quotes=1),
    dict(label='Electrical supplies — project manager approval', stage=2, quotes=2),
    dict(label='Plumbing materials — director approval', stage=3, quotes=3),
    dict(label='Finishing materials — CEO approval', stage=4, quotes=3),
    dict(label='Cement supply — approved, quotations 0 of 3', stage='approved', quotes=0),
    dict(label='Cable supply — approved, quotations 1 of 3', stage='approved', quotes=1),
    dict(label='Steel supply — approved, quotations 2 of 3', stage='approved', quotes=2),
    dict(label='Paint supply — quotations 3 of 3, PO required', stage='approved', quotes=3),
    dict(label='Small tools — no PO required, invoice pending', stage='approved', quotes=0, no_po=True),
    dict(label='Site consumables — no PO, invoice submitted', stage='approved', quotes=0, no_po=True, docs='submitted'),
    dict(label='Safety consumables — accounting received', stage='approved', quotes=3, docs='received'),
    dict(label='Electrical delivery — more invoice documents needed', stage='approved', quotes=3, docs='need_more'),
    dict(label='Plumbing supplies — documents processed', stage='approved', quotes=3, docs='processed'),
    dict(label='Finish samples — invoice documents rejected', stage='approved', quotes=3, docs='rejected'),
    dict(label='Special fitting — single source approved', stage='approved', quotes=1, exception='single_source_approved'),
    dict(label='Urgent repair — quotation exception approved', stage='approved', quotes=2, exception='exception_approved'),
    dict(label='Door hardware — returned for specification correction', stage=2, quotes=2, outcome='returned'),
    dict(label='Duplicate materials — rejected by purchasing', stage=0, quotes=0, outcome='rejected'),
    dict(label='Pump specification — awaiting requester clarification', stage=2, quotes=2, clarification=True),
    dict(label='Pump specification — requester replied', stage=2, quotes=2, replied=True),
    dict(label='Site lighting — overdue at project manager', stage=2, quotes=2, overdue=True),
    dict(label='Urgent safety supplies — approved with CEO override', stage='approved', quotes=3, override=True),
    dict(label='Site tools — invoice uploaded, not submitted', stage='approved', quotes=3, no_po=True, uploaded=True),
    dict(label='Delivery paperwork — new document after submission', stage='approved', quotes=3, docs='submitted', extra_doc=True),
    dict(label='Cable procurement — linked draft RFQ', stage='approved', quotes=3, rfq=True),
    dict(label='Small purchase — no PO, linked draft vendor bill', stage='approved', quotes=1, no_po=True, docs='received', bill=True),
]

MATERIALS = [
    [('Portland cement 50 kg bags', 120), ('Washed construction sand (bags)', 80), ('Concrete curing compound (containers)', 12)],
    [('Safety helmets', 30), ('High visibility vests', 40), ('Protective gloves (pairs)', 100)],
    [('Electrical cable 2.5 mm2 (rolls)', 20), ('Conduit fittings (packs)', 50), ('LED work lights', 12)],
    [('PVC pipe 25 mm (lengths)', 60), ('Isolation valves', 20), ('Pipe fittings (packs)', 35)],
    [('Interior paint 18 L (pails)', 24), ('Paint rollers', 20), ('Masking tape (rolls)', 60)],
    [('Steel reinforcement bundles', 8), ('Binding wire (rolls)', 30), ('Cutting discs', 40)],
]

def line_state(index, case):
    """One current step, completed earlier steps, untouched later steps."""
    stage = case['stage']
    if stage == 'approved':
        return 'approved'
    if index < stage:
        return 'approved'
    if index == stage:
        return case.get('outcome', 'pending')
    return 'waiting'
