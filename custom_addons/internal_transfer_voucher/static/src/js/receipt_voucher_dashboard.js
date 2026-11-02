/** @odoo-module **/
import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';
import { ListController } from '@web/views/list/list_controller';
import { user } from '@web/core/user';
import { BackendListFilters } from './backend_list_filters';
class ReceiptVoucherDashboard extends BackendListFilters {
 static template = 'internal_transfer_voucher.ReceiptVoucherDashboard';
 static cardColors = {"All": "neutral", "Draft": "blue", "Posted": "green", "Cancelled": "red", "Cash": "neutral", "Cheque": "neutral", "Bank Transfer": "neutral", "My Vouchers": "purple", "All Receipts": "neutral", "Planned": "muted", "Awaiting Receipt": "orange", "Received": "teal", "Voucher Created": "blue", "Unfunded": "red"};
 static filterConfig = {"model": "account.receipt.voucher","requestKind": null, "inputs": [{"key":"project","label":"Project (Linked Plan)","field":"cash_plan_line_id.project_id.name"}, {"key": "partner", "label": "Partner", "field": "partner_id.name"}, {"key": "submitter", "label": "Created By", "field": "create_uid.name"}, {"key": "journal", "label": "Journal", "field": "journal_id.name"}, {"key": "from", "label": "Date From", "field": "date", "type": "date", "operator": ">="}, {"key": "to", "label": "Date To", "field": "date", "type": "date", "operator": "<="}]};
 static getCards(context) { return [{"label": "All", "domain": []}, {"label": "Draft", "domain": [["state", "=", "draft"]]}, {"label": "Posted", "domain": [["state", "=", "posted"]]}, {"label": "Cancelled", "domain": [["state", "=", "cancel"]]}, {"label": "Cash", "domain": [["receipt_method", "=", "cash"]]}, {"label": "Cheque", "domain": [["receipt_method", "=", "cheque"]]}, {"label": "Bank Transfer", "domain": [["receipt_method", "=", "bank_transfer"]]}, {"label": "My Vouchers", "domain": [["create_uid", "=", user.userId]]}]; }
}
class ReceiptVoucherListController extends ListController {
 static template = 'internal_transfer_voucher.ReceiptVoucherListView';
 get cardRevision() { return JSON.stringify(this.model.root.records.map(record => [record.resId, record.data.state, record.data.ceo_decision])); }
 static components = {...ListController.components, ReceiptVoucherDashboard};
}
registry.category('views').add('receipt_voucher_dashboard_list', {...listView, Controller: ReceiptVoucherListController});
