from odoo import models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _absar_report_filename(self):
        """Match the PO signing title: number, supplier, MR, project, revision."""
        self.ensure_one()
        parts = [self.name, self.partner_id.name]
        for name in ('material_request_id', 'project_id'):
            if name in self._fields and self[name]:
                parts.append(self[name].name)
        label = ' - '.join(str(part).strip() for part in parts if part and str(part).strip())
        if getattr(self, 'revision', 0):
            label += f'_R{self.revision}'
        return label
