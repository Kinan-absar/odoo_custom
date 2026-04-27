/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Component, onWillStart, useState } from "@odoo/owl";
import { Domain } from "@web/core/domain";

// ─── Dashboard Component ────────────────────────────────────────────────────

class PaymentVoucherDashboard extends Component {
    static template = "internal_transfer_voucher.PaymentVoucherDashboard";
    static props = {
        onFilter: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.data = useState({
            all_count: 0,
            draft_count: 0,
            posted_count: 0,
            cancel_count: 0,
            cash_count: 0,
            cheque_count: 0,
            bank_count: 0,
            transfer_count: 0,
            my_count: 0,
            total_posted_amount: 0,
            currency_symbol: "",
        });

        onWillStart(async () => {
            const result = await this.orm.call(
                "account.payment.voucher",
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

    formatAmount(amount) {
        return Number(amount || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }
}

// ─── Controller ────────────────────────────────────────────────────────────

class PaymentVoucherListController extends ListController {
    static template = "internal_transfer_voucher.PaymentVoucherListView";
    static components = {
        ...ListController.components,
        PaymentVoucherDashboard,
    };

    setup() {
        super.setup();
        this.dashboardState = useState({ domain: [] });
    }

    onDashboardFilter(domain) {
        this.dashboardState.domain = domain;
        // Merge dashboard domain into the model's domain and reload
        const baseDomain = this.props.domain || [];
        const fullDomain = Domain.and([baseDomain, domain]).toList();
        this.model.load({ domain: fullDomain });
    }
}

// ─── View Registration ─────────────────────────────────────────────────────

export const paymentVoucherDashboardListView = {
    ...listView,
    Controller: PaymentVoucherListController,
};

registry.category("views").add(
    "payment_voucher_dashboard_list",
    paymentVoucherDashboardListView
);
