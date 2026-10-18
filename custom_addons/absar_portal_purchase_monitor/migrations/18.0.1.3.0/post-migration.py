import logging
from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Purchase = env['purchase.order'].with_context(active_test=False)
    field = Purchase._fields.get('project_id')
    mapped = 0
    if field and field.type == 'many2one' and field.comodel_name == 'project.project':
        orders = Purchase.search([('absar_portal_project_id', '!=', False), ('project_id', '=', False)])
        for po in orders:
            project = po.absar_portal_project_id
            if not project.company_id or project.company_id == po.company_id:
                po.write({'project_id': project.id})
                mapped += 1
    # Never guess an approver or manufacture approval history for old RFQs.
    legacy = Purchase.search([
        ('absar_portal_preparer_id', '!=', False), ('state', 'in', ['draft', 'sent', 'to approve']),
        ('absar_portal_review_state', '=', 'approved'), ('absar_portal_approver_id', '=', False),
    ])
    legacy.write({'absar_portal_review_state': 'returned',
                  'absar_portal_review_note': 'Please resubmit: this legacy approval has no recorded independent approver.'})
    _logger.info('Purchase workspace upgrade: %s legacy projects mapped; %s legacy RFQs require review', mapped, len(legacy))
