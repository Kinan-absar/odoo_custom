/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { Domain } from "@web/core/domain";

class CashPlanLineDashboard extends Component {
    static template = "internal_transfer_voucher.CashPlanLineDashboard";
    static props = { onFilter: Function };
    setup() {
        this.orm = useService("orm");
        this.data = useState({});
        onWillStart(async () => Object.assign(this.data, await this.orm.call("cash.plan.line", "retrieve_dashboard", [])));
    }
    filter(domain) { this.props.onFilter(domain); }
}

class CashPlanLineListController extends ListController {
    static template = "internal_transfer_voucher.CashPlanLineListView";
    static components = { ...ListController.components, CashPlanLineDashboard };
    setup() { super.setup(); this.dashboardState = useState({ domain: [] }); }
    onDashboardFilter(domain) {
        this.dashboardState.domain = domain;
        this.model.load({ domain: Domain.and([this.props.domain || [], domain]).toList() });
    }
}

registry.category("views").add("cash_plan_line_dashboard_list", { ...listView, Controller: CashPlanLineListController });
