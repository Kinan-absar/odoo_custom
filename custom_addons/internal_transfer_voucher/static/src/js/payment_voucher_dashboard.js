/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

class PaymentVoucherDashboard extends Component {
    static template = "internal_transfer_voucher.PaymentVoucherDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.data = useState({});

        onWillStart(async () => {
            const result = await this.orm.call(
                "account.payment.voucher",
                "retrieve_dashboard",
                []
            );
            Object.assign(this.data, result);
        });
    }

    openFilter(domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Payment Vouchers",
            res_model: "account.payment.voucher",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
        });
    }
}

class PaymentVoucherListController extends ListController {
    static components = {
        ...ListController.components,
        PaymentVoucherDashboard,
    };
}

export const paymentVoucherDashboardListView = {
    ...listView,
    Controller: PaymentVoucherListController,
    buttonTemplate: "internal_transfer_voucher.PaymentVoucherListButtons",
};

registry.category("views").add("payment_voucher_dashboard_list", paymentVoucherDashboardListView);