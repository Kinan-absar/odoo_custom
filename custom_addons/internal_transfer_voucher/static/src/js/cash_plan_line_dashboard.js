/** @odoo-module **/
import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';
import { ListController } from '@web/views/list/list_controller';
import { user } from '@web/core/user';
import { BackendListFilters } from './backend_list_filters';
class CashPlanLineDashboard extends BackendListFilters {
 static template = 'internal_transfer_voucher.CashPlanLineDashboard';
 static cardColors = {"All": "neutral", "Not Submitted": "muted", "Pending CEO": "orange", "Approved": "green", "On Hold": "warning", "Rejected": "red", "Added to Plan": "blue", "Not Added": "purple", "Paid": "teal", "All Receipts": "neutral", "Planned": "muted", "Awaiting Receipt": "orange", "Received": "teal", "Cancelled": "red", "Voucher Created": "blue", "Unfunded": "red"};
 static filterConfig = {"model": "cash.plan.line","requestKind": null, "inputs": [{"key": "partner", "label": "Partner", "field": "partner_id.name"}, {"key": "project", "label": "Project", "field": "project_id.name"}, {"key": "plan", "label": "Weekly Plan", "field": "run_id.name"}, {"key": "category", "label": "Category", "field": "category_id.name"}, {"key": "from", "label": "Date From", "field": "planned_date", "type": "date", "operator": ">="}, {"key": "to", "label": "Date To", "field": "planned_date", "type": "date", "operator": "<="}]};
 static getCards(context) {
    if (context.default_flow_type === 'in') return [
      {label:'All Receipts',domain:[]},
      {label:'Planned',domain:[['state','=','planned']]},
      {label:'Awaiting Receipt',domain:[['state','=','approved']]},
      {label:'Received',domain:[['state','=','executed']]},
      {label:'Cancelled',domain:[['state','=','cancel']]},
      {label:'Added to Plan',domain:[['run_id','!=',false]]},
      {label:'Not Added',domain:[['run_id','=',false]]},
      {label:'Voucher Created',domain:[['receipt_voucher_id','!=',false]]},
    ];
    return [{"label": "All", "domain": []}, {"label": "Not Submitted", "domain": [["ceo_decision", "=", "not_sent"]]}, {"label": "Pending CEO", "domain": [["ceo_decision", "=", "pending"]]}, {"label": "Approved", "domain": [["ceo_decision", "in", ["approved", "adjusted"]]]}, {"label": "On Hold", "domain": [["ceo_decision", "=", "held"]]}, {"label": "Rejected", "domain": [["ceo_decision", "=", "rejected"]]}, {"label": "Added to Plan", "domain": [["run_id", "!=", false]]}, {"label": "Not Added", "domain": [["run_id", "=", false]]}, {"label": "Paid", "domain": [["state", "=", "executed"]]}, {"label": "Cancelled", "domain": [["state", "=", "cancel"]]}, {"label": "Unfunded", "domain": [["funding_status", "=", "unfunded"]]}];
  }
}
class CashPlanLineListController extends ListController {
 static template = 'internal_transfer_voucher.CashPlanLineListView';
 get cardRevision() { return JSON.stringify(this.model.root.records.map(record => [record.resId, record.data.state, record.data.ceo_decision])); }
 static components = {...ListController.components, CashPlanLineDashboard};
}
registry.category('views').add('cash_plan_line_dashboard_list', {...listView, Controller: CashPlanLineListController});
