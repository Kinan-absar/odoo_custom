/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Component, onWillStart, useState } from "@odoo/owl";

class ReceiptVoucherDashboard extends Component {
    static template = "internal_transfer_voucher.ReceiptVoucherDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.data = useState({
            all_count: 0,
            draft_count: 0,
            posted_count: 0,
            cancel_count: 0,
            cash_count: 0,
            cheque_count: 0,
            bank_count: 0,
            my_count: 0,
            total_posted_amount: 0,
            currency_symbol: "",
        });

        onWillStart(async () => {
            const result = await this.orm.call(
                "account.receipt.voucher",
                "retrieve_dashboard",
                []
            );
            Object.assign(this.data, result);
        });
    }

    // Odoo 19: reload current action with a domain filter
    _applyDomain(domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Receipt Vouchers",
            res_model: "account.receipt.voucher",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
            target: "current",
        });
    }

    filterAll()          { this._applyDomain([]); }
    filterDraft()        { this._applyDomain([["state", "=", "draft"]]); }
    filterPosted()       { this._applyDomain([["state", "=", "posted"]]); }
    filterCancelled()    { this._applyDomain([["state", "=", "cancel"]]); }
    filterCash()         { this._applyDomain([["receipt_method", "=", "cash"]]); }
    filterCheque()       { this._applyDomain([["receipt_method", "=", "cheque"]]); }
    filterBankTransfer() { this._applyDomain([["receipt_method", "=", "bank_transfer"]]); }
    filterMyVouchers()   { this._applyDomain([["create_uid", "=", user.userId]]); }

    formatAmount(amount) {
        return Number(amount || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }
}

class ReceiptVoucherListController extends ListController {
    static template = "internal_transfer_voucher.ReceiptVoucherListView";
    static components = {
        ...ListController.components,
        ReceiptVoucherDashboard,
    };
}

export const receiptVoucherDashboardListView = {
    ...listView,
    Controller: ReceiptVoucherListController,
};

registry.category("views").add(
    "receipt_voucher_dashboard_list",
    receiptVoucherDashboardListView
);
