"""Native HR status changes feed the same scoped portal inbox as portal actions."""
from odoo import models
from ..notifications import _PBW_HR_GATEWAY_TOKEN


def _status_updates(records, before):
    if records.env.context.get('pbw_hr_notification_origin') is _PBW_HR_GATEWAY_TOKEN:
        return  # the gateway emits one audited operation, not intermediate writes
    service = records.env['pbw.workspace.notification']
    for record in records:
        if before.get(record.id) != record.state:
            service._notify_hr_event(record, 'state')


class WorkspaceContractNotifications(models.Model):
    _inherit = 'hr.contract'

    def write(self, values):
        before = {rec.id: rec.state for rec in self} if 'state' in values else None
        result = super().write(values)
        if before is not None:
            _status_updates(self, before)
        return result


class WorkspacePayslipNotifications(models.Model):
    _inherit = 'hr.payslip'

    def write(self, values):
        before = {rec.id: rec.state for rec in self} if 'state' in values else None
        result = super().write(values)
        if before is not None:
            _status_updates(self, before)
        return result


class WorkspacePayrollBatchNotifications(models.Model):
    _inherit = 'hr.payslip.run'

    def write(self, values):
        before = {rec.id: rec.state for rec in self} if 'state' in values else None
        result = super().write(values)
        if before is not None:
            _status_updates(self, before)
        return result
