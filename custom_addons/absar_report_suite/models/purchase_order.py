from odoo import models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _absar_report_filename(self):
        """Fallback when an earlier suite replaced the original print expression."""
        self.ensure_one()
        parts = [self.name, self.partner_id.name]
        for name in ('project_id', 'material_request_id'):
            if name in self._fields and self[name]:
                parts.append(self[name].display_name)
        label = ' - '.join(str(part) for part in parts if part)
        return 'RFQ - ' + label if self.state in ('draft', 'sent') else label
