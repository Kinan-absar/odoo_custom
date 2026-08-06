from odoo import _, fields, models
from odoo.exceptions import UserError


def _compute_approval_summary(self):
    Request = self.env['absar.approval.request']
    for record in self:
        requests = (
            Request.search(
                [('res_model', '=', record._name), ('res_id', '=', record.id)],
                order='create_date desc, id desc',
            )
            if record.id
            else Request.browse()
        )
        record.approval_request_ids = requests
        record.approval_request_id = requests[:1]
        record.approval_count = len(requests)


def action_request_approval(self):
    for record in self:
        active = record.approval_request_ids.filtered(
            lambda request: request.state in ('draft', 'in_progress')
        )
        if active:
            raise UserError(_('An active approval request already exists.'))
        request = self.env['absar.approval.request'].create_for_record(record)
        record._approval_engine_started(request)
    return True


def action_approval_approve(self):
    self.ensure_one()
    if not self.approval_request_id:
        raise UserError(_('There is no approval request for this record.'))
    return self.approval_request_id.action_approve()


def action_approval_reject(self):
    self.ensure_one()
    if not self.approval_request_id:
        raise UserError(_('There is no approval request for this record.'))
    return self.approval_request_id.action_reject()


def action_open_approval_requests(self):
    self.ensure_one()
    return {
        'type': 'ir.actions.act_window',
        'name': _('Approval Requests'),
        'res_model': 'absar.approval.request',
        'view_mode': 'list,form',
        'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
        'context': {'create': False},
    }


def _approval_engine_started(self, request):
    return True


def _approval_engine_approved(self, request):
    self.ensure_one()
    return request.workflow_id.execute_target_action(self, 'approved')


def _approval_engine_rejected(self, request, reason):
    self.ensure_one()
    return request.workflow_id.execute_target_action(self, 'rejected')


def _approval_fields_and_methods():
    """Return fresh field instances and shared methods for one target model.

    Every integrated model receives its own field objects. This deliberately
    avoids Odoo multiple model inheritance, which can duplicate fields such as
    mail.thread's attachment_ids on models that already use chatter.
    """
    return {
        'approval_request_ids': fields.Many2many(
            'absar.approval.request',
            compute='_compute_approval_summary',
            string='Approval Requests',
            readonly=True,
        ),
        'approval_request_id': fields.Many2one(
            'absar.approval.request',
            compute='_compute_approval_summary',
            string='Current Approval',
            readonly=True,
        ),
        'approval_state': fields.Selection(
            related='approval_request_id.state',
            string='Approval Status',
            readonly=True,
        ),
        'approval_stage_id': fields.Many2one(
            related='approval_request_id.stage_id',
            string='Approval Stage',
            readonly=True,
        ),
        'approval_count': fields.Integer(
            compute='_compute_approval_summary',
            string='Approval Count',
            readonly=True,
        ),
        'approval_can_approve': fields.Boolean(
            related='approval_request_id.can_current_user_approve',
            string='Can Approve',
            readonly=True,
        ),
        'approval_can_reject': fields.Boolean(
            related='approval_request_id.can_current_user_reject',
            string='Can Reject',
            readonly=True,
        ),
        '_compute_approval_summary': _compute_approval_summary,
        'action_request_approval': action_request_approval,
        'action_approval_approve': action_approval_approve,
        'action_approval_reject': action_approval_reject,
        'action_open_approval_requests': action_open_approval_requests,
        '_approval_engine_started': _approval_engine_started,
        '_approval_engine_approved': _approval_engine_approved,
        '_approval_engine_rejected': _approval_engine_rejected,
    }


class EmployeeRequest(models.Model):
    _inherit = 'employee.request'
    locals().update(_approval_fields_and_methods())


class MaterialRequest(models.Model):
    _inherit = 'material.request'
    locals().update(_approval_fields_and_methods())


class PettyCash(models.Model):
    _inherit = 'petty.cash'
    locals().update(_approval_fields_and_methods())


class PortalVendorInvoice(models.Model):
    _inherit = 'portal.vendor.invoice'
    locals().update(_approval_fields_and_methods())


class ConstructionContract(models.Model):
    _inherit = 'construction.contract'
    locals().update(_approval_fields_and_methods())


class AccountPaymentVoucher(models.Model):
    _inherit = 'account.payment.voucher'
    locals().update(_approval_fields_and_methods())


class AccountReceiptVoucher(models.Model):
    _inherit = 'account.receipt.voucher'
    locals().update(_approval_fields_and_methods())


class AccountInternalTransfer(models.Model):
    _inherit = 'account.internal.transfer'
    locals().update(_approval_fields_and_methods())


class CashPlanRun(models.Model):
    _inherit = 'cash.plan.run'
    locals().update(_approval_fields_and_methods())


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    locals().update(_approval_fields_and_methods())
