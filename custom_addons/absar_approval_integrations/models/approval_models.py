from odoo import models


class EmployeeRequest(models.Model):
    _inherit = ['employee.request', 'absar.approval.engine.mixin']


class MaterialRequest(models.Model):
    _inherit = ['material.request', 'absar.approval.engine.mixin']


class PettyCash(models.Model):
    _inherit = ['petty.cash', 'absar.approval.engine.mixin']


class PortalVendorInvoice(models.Model):
    _inherit = ['portal.vendor.invoice', 'absar.approval.engine.mixin']


class ConstructionContract(models.Model):
    _inherit = ['construction.contract', 'absar.approval.engine.mixin']


class AccountPaymentVoucher(models.Model):
    _inherit = ['account.payment.voucher', 'absar.approval.engine.mixin']


class AccountReceiptVoucher(models.Model):
    _inherit = ['account.receipt.voucher', 'absar.approval.engine.mixin']


class AccountInternalTransfer(models.Model):
    _inherit = ['account.internal.transfer', 'absar.approval.engine.mixin']


class CashPlanRun(models.Model):
    _inherit = ['cash.plan.run', 'absar.approval.engine.mixin']


class PurchaseOrder(models.Model):
    _inherit = ['purchase.order', 'absar.approval.engine.mixin']
