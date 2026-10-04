/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { Domain } from "@web/core/domain";

class MaterialRequestDashboard extends Component {
    static template = "employee_portal_suite.MaterialRequestDashboard";
    static props = { onFilter: Function };

    setup() {
        this.orm = useService("orm");
        this.cards = useState([]);
        onWillStart(async () => {
            const result = await this.orm.call(
                "employee.portal.backend.filter.card",
                "get_dashboard_cards",
                ["material"]
            );
            this.cards.splice(0, this.cards.length, ...result);
        });
    }

    filter(domain) {
        this.props.onFilter(domain || []);
    }
}

class MaterialRequestListController extends ListController {
    static template = "employee_portal_suite.MaterialRequestListView";
    static components = { ...ListController.components, MaterialRequestDashboard };

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

export const materialRequestDashboardListView = {
    ...listView,
    Controller: MaterialRequestListController,
};

registry.category("views").add("material_request_dashboard_list", materialRequestDashboardListView);
