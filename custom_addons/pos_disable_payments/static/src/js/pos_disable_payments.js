/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { NumpadWidget } from "@point_of_sale/app/components/numpad/numpad";
import { useState, useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { PosStore } from "@point_of_sale/app/store/pos_store";

// ─── Helper: fetch access flags for the current cashier ───────────────────────
async function loadAccessFlags(orm, employeeId) {
    try {
        const flags = await orm.call(
            "pos.session",
            "get_pos_ui_pos_disable_payments",
            [employeeId || 0]
        );
        return flags;
    } catch {
        // Fallback: allow everything
        return {
            pos_allow_payment: true,
            pos_allow_discount: true,
            pos_allow_edit_price: true,
            pos_allow_qty: true,
            pos_allow_remove_line: true,
            pos_allow_customer: true,
            pos_allow_numpad: true,
            pos_allow_plus_minus: true,
        };
    }
}

// ─── Patch PosStore to load/update flags on employee switch ───────────────────
patch(PosStore.prototype, {
    setup() {
        super.setup(...arguments);
        this.posAccessFlags = {
            pos_allow_payment: true,
            pos_allow_discount: true,
            pos_allow_edit_price: true,
            pos_allow_qty: true,
            pos_allow_remove_line: true,
            pos_allow_customer: true,
            pos_allow_numpad: true,
            pos_allow_plus_minus: true,
        };
    },

    async setCashier(employee) {
        const result = await super.setCashier(...arguments);
        const employeeId = employee && employee.id ? employee.id : 0;
        this.posAccessFlags = await loadAccessFlags(this.orm, employeeId);
        return result;
    },

    getAccessFlags() {
        return this.posAccessFlags;
    },
});

// ─── Patch PaymentScreen: hide button when payment is not allowed ─────────────
patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
    },

    get isPaymentAllowed() {
        return this.pos.getAccessFlags().pos_allow_payment;
    },
});

// ─── Patch ProductScreen: enforce various restrictions ────────────────────────
patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
    },

    get canEditPrice() {
        return this.pos.getAccessFlags().pos_allow_edit_price;
    },

    get canEditQty() {
        return this.pos.getAccessFlags().pos_allow_qty;
    },

    get canRemoveLine() {
        return this.pos.getAccessFlags().pos_allow_remove_line;
    },

    get canSelectCustomer() {
        return this.pos.getAccessFlags().pos_allow_customer;
    },

    get canApplyDiscount() {
        return this.pos.getAccessFlags().pos_allow_discount;
    },

    // Override deleteOrderLine to enforce remove_line restriction
    deleteOrderLine(event, orderLine) {
        if (!this.pos.getAccessFlags().pos_allow_remove_line) {
            this.notification.add(
                this.env._t("You are not allowed to remove order lines."),
                { type: "danger" }
            );
            return;
        }
        return super.deleteOrderLine(...arguments);
    },
});

// ─── Patch NumpadWidget: disable numpad when not allowed ──────────────────────
patch(NumpadWidget.prototype, {
    get isNumpadAllowed() {
        return this.pos.getAccessFlags().pos_allow_numpad;
    },
});
