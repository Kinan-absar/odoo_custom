/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { Domain } from "@web/core/domain";

class EmployeeRequestDashboard extends Component {
    static template = "employee_portal_suite.EmployeeRequestDashboard";
    static props = { onFilter: Function };

    setup() {
        this.orm = useService("orm");
        this.cards = useState([]);
        onWillStart(async () => {
            const result = await this.orm.call(
                "employee.portal.backend.filter.card",
                "get_dashboard_cards",
                ["employee"]
            );
            this.cards.splice(0, this.cards.length, ...result);
        });
    }

    filter(domain) {
        this.props.onFilter(domain || []);
    }
}

class EmployeeRequestListController extends ListController {
    static template = "employee_portal_suite.EmployeeRequestListView";
    static components = { ...ListController.components, EmployeeRequestDashboard };

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

export const employeeRequestDashboardListView = {
    ...listView,
    Controller: EmployeeRequestListController,
};

registry.category("views").add("employee_request_dashboard_list", employeeRequestDashboardListView);
