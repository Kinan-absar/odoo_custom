/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

// ─── Discount Dialog ──────────────────────────────────────────────────────────
export class BiPosDiscountDialog extends Component {
    static template = "bi_pos_discount.DiscountDialog";
    static props = {
        close: Function,
        discountType: String,
        defaultValue: { type: Number, optional: true },
        onConfirm: Function,
    };

    setup() {
        this.state = useState({
            value: this.props.defaultValue || "",
        });
    }

    get title() {
        return this.props.discountType === "fixed"
            ? _t("Fixed Amount Discount")
            : _t("Percentage Discount");
    }

    get placeholder() {
        return this.props.discountType === "fixed" ? "0.00" : "0 – 100";
    }

    get suffix() {
        return this.props.discountType === "fixed" ? "" : "%";
    }

    onInput(event) {
        this.state.value = event.target.value;
    }

    confirm() {
        const val = parseFloat(this.state.value);
        if (isNaN(val) || val < 0) {
            return;
        }
        if (this.props.discountType === "percentage" && val > 100) {
            return;
        }
        this.props.onConfirm(val);
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}

// ─── Patch PosOrder to carry discount metadata ────────────────────────────────
patch(PosOrder.prototype, {
    setup() {
        super.setup(...arguments);
        this.biDiscountType = null;
        this.biDiscountValue = 0;
        this.biDiscountAmount = 0;
    },

    /**
     * Apply a global discount on all order lines.
     * - percentage: apply as Odoo native discount (%) on each line
     * - fixed: spread the fixed discount proportionally across lines
     */
    applyBiDiscount(discountType, discountValue) {
        const lines = this.orderlines;
        if (!lines || lines.length === 0) return;

        this.biDiscountType = discountType;
        this.biDiscountValue = discountValue;

        if (discountType === "percentage") {
            // Apply to each line's native discount field
            lines.forEach((line) => {
                line.set_discount(discountValue);
            });
            // Compute total discount amount for reporting
            this.biDiscountAmount = lines.reduce((acc, line) => {
                const base = line.get_unit_price() * line.get_quantity();
                return acc + base * (discountValue / 100);
            }, 0);
        } else if (discountType === "fixed") {
            const subtotal = lines.reduce((acc, line) => {
                return acc + line.get_unit_price() * line.get_quantity();
            }, 0);

            if (subtotal <= 0) return;

            // Cap fixed discount to the order subtotal
            const cappedDiscount = Math.min(discountValue, subtotal);
            this.biDiscountAmount = cappedDiscount;

            // Distribute proportionally
            lines.forEach((line) => {
                const lineSubtotal = line.get_unit_price() * line.get_quantity();
                const proportion = lineSubtotal / subtotal;
                const lineDiscount = (cappedDiscount * proportion * 100) / lineSubtotal;
                line.set_discount(Math.min(lineDiscount, 100));
            });
        }
    },

    removeBiDiscount() {
        this.biDiscountType = null;
        this.biDiscountValue = 0;
        this.biDiscountAmount = 0;
        this.orderlines.forEach((line) => line.set_discount(0));
    },

    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.bi_discount_type = this.biDiscountType;
        json.bi_discount_value = this.biDiscountValue;
        json.bi_discount_amount = this.biDiscountAmount;
        return json;
    },
});

// ─── Patch ProductScreen to add Discount button ───────────────────────────────
patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialog = useService("dialog");
    },

    get showBiDiscountButton() {
        return this.pos.config.bi_show_discount_button;
    },

    openBiDiscountDialog() {
        const config = this.pos.config;
        this.dialog.add(BiPosDiscountDialog, {
            discountType: config.bi_discount_type || "percentage",
            defaultValue: config.bi_discount_value || 0,
            onConfirm: (value) => {
                const order = this.pos.get_order();
                if (order) {
                    order.applyBiDiscount(config.bi_discount_type, value);
                }
            },
        });
    },

    removeBiDiscount() {
        const order = this.pos.get_order();
        if (order) {
            order.removeBiDiscount();
        }
    },

    get currentBiDiscount() {
        const order = this.pos.get_order();
        if (!order || !order.biDiscountType) return null;
        if (order.biDiscountType === "percentage") {
            return `${order.biDiscountValue}%`;
        }
        return this.env.utils.formatCurrency(order.biDiscountAmount);
    },
});
