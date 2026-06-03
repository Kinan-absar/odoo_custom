/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Component, onWillStart, useState } from "@odoo/owl";
import { Domain } from "@web/core/domain";

// ─── Dashboard Component ────────────────────────────────────────────────────

class EmployeeRequestDashboard extends Component {
    static template = "employee_portal_suite.EmployeeRequestDashboard";
    static props = {
        onFilter: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.data = useState({
            all_count: 0,
            draft_count: 0,
            manager_count: 0,
            hr_count: 0,
            finance_count: 0,
            ceo_count: 0,
            approved_count: 0,
            rejected_count: 0,
            my_count: 0,
            leave_count: 0,
            advance_count: 0,
            other_count: 0,
        });

        onWillStart(async () => {
            const result = await this.orm.call(
                "employee.request",
                "retrieve_dashboard",
                []
            );
            Object.assign(this.data, result);
        });
    }

    filter(domain) {
        this.props.onFilter(domain);
    }

    get myDomain() {
        return [["create_uid", "=", user.userId]];
    }
}

// ─── Controller ────────────────────────────────────────────────────────────

class EmployeeRequestListController extends ListController {
    static template = "employee_portal_suite.EmployeeRequestListView";
    static components = {
        ...ListController.components,
        EmployeeRequestDashboard,
    };

    setup() {
        super.setup();
        this.dashboardState = useState({ domain: [] });
    }

    onDashboardFilter(domain) {
        this.dashboardState.domain = domain;
        const baseDomain = this.props.domain || [];
        const fullDomain = Domain.and([baseDomain, domain]).toList();
        this.model.load({ domain: fullDomain });
    }
}

// ─── View Registration ─────────────────────────────────────────────────────

export const employeeRequestDashboardListView = {
    ...listView,
    Controller: EmployeeRequestListController,
};

registry.category("views").add(
    "employee_request_dashboard_list",
    employeeRequestDashboardListView
);
