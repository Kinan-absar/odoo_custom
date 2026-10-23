import json
import math
from odoo import models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class PurchaseOrderReceipt(models.Model):
    _inherit = 'purchase.order'

    def _portal_receipt_access(self):
        self.ensure_one()
        user = self._portal_actor('preparer')
        self._portal_check_company(user)
        if self.state not in ('purchase', 'done'):
            raise UserError(_('Approve the purchase order before receiving products.'))
        if (not user.has_group('absar_portal_purchase_monitor.group_portal_purchase_user') and
                self.absar_portal_preparer_id != user):
            raise UserError(_('You can only receive products for your own purchase orders.'))
        return user

    def _portal_receipt_moves(self, picking):
        return picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')).sorted('id')

    def _portal_receipt_problem(self, picking):
        self.ensure_one()
        if (picking.company_id != self.company_id or picking not in self.picking_ids or
                picking.picking_type_id.code != 'incoming' or picking.location_id.usage != 'supplier'):
            raise UserError(_('This receipt does not belong to this purchase order.'))
        moves = self._portal_receipt_moves(picking)
        if any(m.purchase_line_id.order_id != self for m in moves):
            return _('This receipt contains another purchase order or an unrelated stock move. Complete it in Inventory.')
        if picking.state in ('done', 'cancel') or not moves:
            return _('This receipt is already completed or cancelled. Reload the purchase order.')
        return ''

    def _portal_receipt_version(self, picking):
        moves = self._portal_receipt_moves(picking)
        return json.dumps([str(picking.write_date),
            [(m.id, str(m.write_date), m.product_uom_qty, m.quantity, m.picked) for m in moves],
            [(l.id, str(l.write_date), l.quantity, l.lot_id.id, l.lot_name or '')
             for l in moves.move_line_ids.sorted('id')]], separators=(',', ':'))

    def _portal_receipts(self):
        self._portal_receipt_access()
        receipts = []
        for picking in self.sudo().picking_ids.filtered(lambda p:
                p.company_id == self.company_id and p.picking_type_id.code == 'incoming' and
                p.location_id.usage == 'supplier' and p.state not in ('done', 'cancel')).sorted('id'):
            problem = self._portal_receipt_problem(picking)
            rows = []
            for move in self._portal_receipt_moves(picking):
                tracked = move.product_id.tracking != 'none'
                lots = move.move_line_ids.filtered(lambda l: l.lot_id or l.lot_name)
                rows.append(dict(id=move.id, product=move.product_id.display_name,
                    description=move.name or '', expected=move.product_uom_qty,
                    uom=move.product_uom.display_name, rounding=move.product_uom.rounding,
                    tracking=move.product_id.tracking,
                    lot_ready=not tracked or bool(lots),
                    already_received=move.purchase_line_id.qty_received))
            receipts.append(dict(id=picking.id, name=picking.name, state=picking.state,
                version=self._portal_receipt_version(picking), problem=problem, lines=rows,
                backorder_policy=picking.picking_type_id.create_backorder))
        return receipts

    def _portal_receive(self, receipt_id, version, quantities):
        """Validate one scoped native receipt, never write PO received totals."""
        self._portal_lock()
        self._portal_receipt_access()
        if isinstance(receipt_id, bool) or not isinstance(receipt_id, int) or receipt_id <= 0:
            raise ValidationError(_('Choose a valid receipt.'))
        picking = self.sudo().picking_ids.filtered(lambda p: p.id == receipt_id)
        if len(picking) != 1:
            raise UserError(_('This receipt does not belong to this purchase order.'))
        self.env.cr.execute('SELECT id FROM stock_picking WHERE id=%s FOR UPDATE', [picking.id])
        picking.invalidate_recordset()
        moves = self._portal_receipt_moves(picking)
        if moves:
            self.env.cr.execute('SELECT id FROM stock_move WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(moves.ids)])
            moves.invalidate_recordset()
            # Serialized move-line versions cover native lot and quantity edits.
            lines = moves.move_line_ids
            if lines:
                self.env.cr.execute('SELECT id FROM stock_move_line WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(lines.ids)])
                lines.invalidate_recordset()
        problem = self._portal_receipt_problem(picking)
        if problem:
            raise UserError(problem)
        if not version or version != self._portal_receipt_version(picking):
            raise UserError(_('This receipt changed since you opened it. Close and reopen Receive Products.'))
        if not isinstance(quantities, list) or len(quantities) > 300:
            raise ValidationError(_('Invalid receipt quantities.'))
        selected = {}
        for row in quantities:
            if not isinstance(row, dict):
                raise ValidationError(_('Invalid receipt line.'))
            ident, qty = row.get('id'), row.get('quantity')
            if isinstance(ident, bool) or not isinstance(ident, int) or ident in selected:
                raise ValidationError(_('Invalid or duplicate receipt line.'))
            if isinstance(qty, bool) or not isinstance(qty, (int, float)) or not math.isfinite(qty) or qty < 0:
                raise ValidationError(_('Received quantities must be finite, non-negative numbers.'))
            selected[ident] = qty
        if set(selected) != set(moves.ids):
            raise ValidationError(_('Receipt lines changed or do not belong to this receipt. Reopen Receive Products.'))
        positive = False
        for move in moves:
            qty = selected[move.id]
            if float_compare(qty, move.product_uom_qty, precision_rounding=move.product_uom.rounding) > 0:
                raise ValidationError(_('Received quantity exceeds the remaining demand for %s.') % move.product_id.display_name)
            receiving = float_compare(qty, 0, precision_rounding=move.product_uom.rounding) > 0
            positive = positive or receiving
            if receiving and move.product_id.tracking != 'none' and not move.move_line_ids.filtered(lambda l: l.lot_id or l.lot_name):
                raise UserError(_('Assign lots or serial numbers for %s in Inventory before validating its receipt.') % move.product_id.display_name)
            if (float_compare(qty, move.product_uom_qty, precision_rounding=move.product_uom.rounding) < 0 and
                    picking.picking_type_id.create_backorder == 'never'):
                raise UserError(_('This operation type cancels unreceived quantities. For a partial receipt with quantities kept pending, change its backorder setting in Inventory first.'))
        if not positive:
            raise ValidationError(_('Enter a received quantity greater than zero on at least one line.'))
        # Set every active move explicitly, including zero quantities: native
        # prefilled/reserved quantities must never receive unselected products.
        for move in moves:
            qty = selected[move.id]
            move.sudo().with_company(self.company_id).write({'quantity': qty, 'picked': qty > 0})
        result = picking.sudo().with_company(self.company_id).button_validate()
        if (isinstance(result, dict) and result.get('res_model') == 'stock.backorder.confirmation' and
                picking.state != 'done'):
            # Use the native keep-backorder decision, preserving unreceived demand.
            ctx = dict(result.get('context') or {})
            wizard = self.env['stock.backorder.confirmation'].sudo().with_company(self.company_id).with_context(**ctx).create({
                'pick_ids': [(6, 0, picking.ids)]})
            result = wizard.process()
        picking.invalidate_recordset()
        if picking.state != 'done':
            raise UserError(_('This receipt requires an additional Inventory step. No quantities were saved; complete the receipt in Inventory.'))
        self.invalidate_recordset()
        return {'receipt': picking.name, 'state': picking.state}
