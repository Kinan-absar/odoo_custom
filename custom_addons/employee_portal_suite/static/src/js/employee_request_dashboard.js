/** @odoo-module **/
import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';
import { ListController } from '@web/views/list/list_controller';
import { user } from '@web/core/user';
import { BackendListFilters } from './backend_list_filters';
class EmployeeRequestDashboard extends BackendListFilters {
 static template = 'employee_portal_suite.EmployeeRequestDashboard';
 static filterConfig = {"model": "employee.request","requestKind": "employee", "inputs": [{"key": "employee", "label": "Employee", "field": "employee_id.name"}, {"key": "submitter", "label": "Submitted By", "field": "create_uid.name"}, {"key": "project", "label": "Project", "field": "project_id.name"}, {"key": "from", "label": "Date From", "field": "request_date", "type": "date", "operator": ">="}, {"key": "to", "label": "Date To", "field": "request_date", "type": "date", "operator": "<="}]};
 static getCards(context) { return []; }
}
class EmployeeRequestListController extends ListController {
 static template = 'employee_portal_suite.EmployeeRequestListView';
 get cardRevision() { return JSON.stringify(this.model.root.records.map(record => [record.resId, record.data.state, record.data.ceo_decision])); }
 static components = {...ListController.components, EmployeeRequestDashboard};
}
registry.category('views').add('employee_request_dashboard_list', {...listView, Controller: EmployeeRequestListController});
