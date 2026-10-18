import ast
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .native_access import native_portal, guard_actor
from .native_view import prepare_native_arch

# An identity token cannot be supplied by a JSON-RPC caller as a context boolean.
_SENT_OPERATION = object()


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    absar_native_can_edit = fields.Boolean(compute='_compute_absar_native_can_edit')

    @api.depends_context('uid')
    @api.depends('state', 'absar_portal_preparer_id', 'absar_portal_review_state')
    def _compute_absar_native_can_edit(self):
        for po in self:
            po.absar_native_can_edit = not native_portal(self.env) or (
                bool(self.env.user.has_group('absar_portal_purchase_monitor.group_portal_purchase_preparer'))
                and (not po._origin.id or po._portal_editable(self.env.user)))

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        if native_portal(self.env) and not self.env.su:
            if 'user_id' in fields_list:
                result['user_id'] = False
            if 'company_id' in fields_list:
                result['company_id'] = self.env.company.id
        return result

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if native_portal(self.env):
            arch = prepare_native_arch(arch, purchase=True)
            preparer = self.env.user.has_group('absar_portal_purchase_monitor.group_portal_purchase_preparer')
            arch.set('delete', 'false')
            if not preparer:
                arch.set('create', 'false')
                arch.set('edit', 'false')
            if view_type == 'form':
                for node in arch.xpath('.//sheet//field[not(ancestor::field)]'):
                    if node.get('name') == 'absar_native_can_edit':
                        continue
                    previous = node.get('readonly', 'False')
                    node.set('readonly', '(%s) or not absar_native_can_edit' % previous)
        return arch, view

    def action_open_absar_portal_return(self):
        self.ensure_one()
        guard_actor(self.env, 'approver') if native_portal(self.env) else self._portal_actor('approver')
        if native_portal(self.env):
            self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Return RFQ for Correction'),
                'res_model': 'absar.portal.purchase.return', 'view_mode': 'form',
                'views': [(self.env.ref('absar_portal_purchase_monitor.portal_return_form').id, 'form')],
                'target': 'new', 'context': {'default_purchase_id': self.id}}

    def print_quotation(self):
        if native_portal(self.env) and not self.env.su:
            self.ensure_one()
            self.check_access('read')
            if not self._portal_editable(guard_actor(self.env, 'preparer')):
                raise AccessError(_('Print RFQ is available on your editable draft. Use the Print menu for approved orders.'))
            # Native print_quotation writes only draft -> sent before rendering.
            return super(PurchaseOrder, self.with_context(absar_native_sent=_SENT_OPERATION)).print_quotation()
        return super().print_quotation()

    def write(self, vals):
        if (native_portal(self.env) and not self.env.su and
                self.env.context.get('absar_native_sent') is _SENT_OPERATION and vals == {'state': 'sent'}):
            user = guard_actor(self.env, 'preparer')
            for po in self:
                po.check_access('read')
                po._portal_lock()
                if not po._portal_editable(user):
                    raise AccessError(_('Only your editable RFQ may be marked as sent.'))
            # Bypass only the field whitelist for this server-authorized transition;
            # preserve all native write hooks and tracking through the same model.
            return super(PurchaseOrder, self.sudo()).write(vals)
        return super().write(vals)

    def action_rfq_send(self):
        if native_portal(self.env) and not self.env.su:
            self.ensure_one()
            self.check_access('read')
            if not self._portal_editable(guard_actor(self.env, 'preparer')):
                raise AccessError(_('Email composition is available on your editable draft RFQ.'))
        return super().action_rfq_send()


class PurchaseReturn(models.TransientModel):
    _name = 'absar.portal.purchase.return'
    _description = 'Return Portal Purchase RFQ'

    purchase_id = fields.Many2one('purchase.order', required=True, readonly=True)
    note = fields.Text(required=True, string='Correction required')

    def action_return(self):
        self.ensure_one()
        po = self.purchase_id
        user = po._portal_actor('approver')
        if native_portal(self.env):
            po.check_access('read')
        po._portal_lock()
        po._portal_check_company(user)
        if (po.absar_portal_preparer_id == user or not po.absar_portal_preparer_id or
                po.state not in ('draft', 'sent') or po.absar_portal_review_state not in ('submitted', 'approved')):
            raise UserError(_('Only another preparer’s submitted or approved RFQ may be returned.'))
        if not (self.note or '').strip():
            raise UserError(_('Describe the correction required.'))
        po.sudo().write({'absar_portal_review_note': self.note.strip()})
        po.action_absar_portal_return()
        return {'type': 'ir.actions.act_window_close'}


class MaterialRequest(models.Model):
    _inherit = 'material.request'

    def action_workflow_approve(self):
        if native_portal(self.env) and not self.env.su:
            # EPS accepts an actor context for its controlled internal calls.
            # A browser RPC caller must never impersonate that actor.
            return super(MaterialRequest, self.with_context(workflow_actor_user_id=self.env.uid)).action_workflow_approve()
        return super().action_workflow_approve()

    def action_workflow_reject(self):
        if native_portal(self.env) and not self.env.su:
            return super(MaterialRequest, self.with_context(workflow_actor_user_id=self.env.uid)).action_workflow_reject()
        return super().action_workflow_reject()

    def action_create_po(self):
        if native_portal(self.env) and not self.env.su:
            self.ensure_one()
            user = guard_actor(self.env, 'preparer')
            self.check_access('read')
            if (self.state != 'approved' or self.no_po_required or
                    self.project_id not in user.absar_purchase_project_ids or
                    ((self.project_id.company_id or self.employee_id.company_id) not in user.company_ids)):
                raise AccessError(_('Choose an approved Material Request assigned to your projects and requiring a PO.'))
        action = super().action_create_po()
        if native_portal(self.env):
            action = dict(action, context=dict(action.get('context') or {}, default_project_id=self.project_id.id,
                                               default_company_id=(self.project_id.company_id or self.employee_id.company_id).id or self.env.company.id))
        return action


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    def _native_purchase_targets(self, vals=None):
        vals = vals or {}
        model = vals.get('model', self.model if self else self.env.context.get('default_model'))
        raw_ids = vals.get('res_ids', self.res_ids if self else self.env.context.get('default_res_ids', []))
        try:
            ids = ast.literal_eval(raw_ids) if isinstance(raw_ids, str) else raw_ids
            if not isinstance(ids, (list, tuple)) or len(ids) != 1 or type(ids[0]) is not int:
                raise ValueError()
        except (ValueError, SyntaxError, TypeError):
            raise AccessError(_('Compose one purchase RFQ at a time.'))
        if model != 'purchase.order' or vals.get('composition_mode', self.composition_mode if self else self.env.context.get('default_composition_mode', 'comment')) != 'comment':
            raise AccessError(_('Only single RFQ email composition is available here.'))
        order = self.env[model].browse(ids)
        user = guard_actor(self.env, 'preparer')
        order.check_access('read')
        if not order._portal_editable(user):
            raise AccessError(_('Only your own editable RFQ can be emailed here.'))
        return order

    @api.model_create_multi
    def create(self, vals_list):
        if native_portal(self.env) and not self.env.su:
            for vals in vals_list:
                self._native_purchase_targets(vals)
        return super().create(vals_list)

    def write(self, vals):
        if native_portal(self.env) and not self.env.su:
            for wizard in self:
                wizard._native_purchase_targets(vals)
        return super().write(vals)

    def action_send_mail(self):
        if native_portal(self.env) and not self.env.su:
            for wizard in self:
                wizard._native_purchase_targets()
            return super(MailComposeMessage, self.with_context(absar_native_sent=_SENT_OPERATION)).action_send_mail()
        return super().action_send_mail()

    def create_mail_template(self):
        if native_portal(self.env) and not self.env.su:
            raise AccessError(_('Email template administration requires an internal user.'))
        return super().create_mail_template()
