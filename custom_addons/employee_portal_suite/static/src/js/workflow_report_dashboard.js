/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { Domain } from "@web/core/domain";

class WorkflowReportDashboard extends Component {
    static template = "employee_portal_suite.WorkflowReportDashboard";
    static props = { onFilter: Function, onNavigate: Function };

    setup() {
        this.orm = useService("orm");
        this.data = useState({
            all_count: 0, pending_count: 0, waiting_count: 0, overdue_count: 0,
            approved_count: 0, returned_count: 0, rejected_count: 0, skipped_count: 0,
            override_count: 0, avg_hours: 0, active_workflow_count: 0,
            approval_role_count: 0, active_delegation_count: 0,
        });
        onWillStart(() => this.refresh());
    }

    async refresh() {
        const values = await this.orm.call(
            "employee.portal.workflow.approval.line",
            "retrieve_workflow_dashboard",
            []
        );
        Object.assign(this.data, values);
    }

    filter(domain) { this.props.onFilter(domain); }
    navigate(xmlid) { this.props.onNavigate(xmlid); }
}

class WorkflowReportListController extends ListController {
    static template = "employee_portal_suite.WorkflowReportListView";
    static components = { ...ListController.components, WorkflowReportDashboard };

    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    onDashboardFilter(domain) {
        const baseDomain = this.props.domain || [];
        const fullDomain = Domain.and([baseDomain, domain]).toList();
        this.model.load({ domain: fullDomain });
    }

    onDashboardNavigate(xmlid) { this.actionService.doAction(xmlid); }
}

export const workflowReportDashboardListView = { ...listView, Controller: WorkflowReportListController };
registry.category("views").add("workflow_report_dashboard_list", workflowReportDashboardListView);
