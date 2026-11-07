/** @odoo-module **/
import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';
import { ListController } from '@web/views/list/list_controller';
import { user } from '@web/core/user';
import { BackendListFilters } from './backend_list_filters';
class MaterialRequestDashboard extends BackendListFilters {
 static template = 'portal_backend_workspace.foundation__MaterialRequestDashboard';
 static filterConfig = {"model": "material.request","requestKind": "material", "inputs": [{"key": "employee", "label": "Employee", "field": "employee_id.name"}, {"key": "submitter", "label": "Submitted By", "field": "create_uid.name"}, {"key": "project", "label": "Project", "field": "project_id.name"}, {"key": "from", "label": "Date From", "field": "request_date", "type": "date", "operator": ">="}, {"key": "to", "label": "Date To", "field": "request_date", "type": "date", "operator": "<="}]};
 static getCards(context) { return []; }
}
class MaterialRequestListController extends ListController {
 static template = 'portal_backend_workspace.foundation__MaterialRequestListView';
 get cardRevision() { return JSON.stringify(this.model.root.records.map(record => [record.resId, record.data.state, record.data.ceo_decision])); }
 static components = {...ListController.components, MaterialRequestDashboard};
}
registry.category('views').add('material_request_dashboard_list', {...listView, Controller: MaterialRequestListController});
