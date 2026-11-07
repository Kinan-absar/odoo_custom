from odoo import models, fields

class MaterialRequestLine(models.Model):
    _name = 'material.request.line'
    _description = 'Material Request Line'

    request_id = fields.Many2one('material.request', required=True, ondelete="cascade")

    item_name = fields.Char("Item")
    qty_required = fields.Float("Required Quantity")
    uom_id = fields.Many2one('uom.uom', string="UoM")
