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
        this.user = useService("user");
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

    setDashboardDomain(domain, label) {
        this.env.searchModel.setDomainParts({
            payment_voucher_dashboard: {
                domain: domain,
                facetLabel: label,
            },
        });
    }

    clearDashboardDomain() {
        this.env.searchModel.setDomainParts({
            payment_voucher_dashboard: null,
        });
    }

    filterMyVouchers() {
        // Use user service instead of context.uid (context is undefined in OWL 2)
        this.setDashboardDomain(
            [['create_uid', '=', this.user.userId]],
            'My Vouchers'
        );
    }

    formatAmount(amount) {
        return Number(amount || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }
}

class PaymentVoucherListController extends ListController {
    static template = "internal_transfer_voucher.PaymentVoucherListView";
    static components = {
        ...ListController.components,
        PaymentVoucherDashboard,
    };
}

export const paymentVoucherDashboardListView = {
    ...listView,
    Controller: PaymentVoucherListController,
};

registry.category("views").add(
    "payment_voucher_dashboard_list",
    paymentVoucherDashboardListView
);
