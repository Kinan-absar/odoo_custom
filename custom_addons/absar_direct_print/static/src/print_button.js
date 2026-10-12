/** @odoo-module **/
import { onWillStart, useState, useSubEnv } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { FormCompiler } from "@web/views/form/form_compiler";
import { createElement } from "@web/core/utils/xml";
import { ListController } from "@web/views/list/list_controller";

function setupPrint(controller, viewType) {
    controller.absarPrint = useState({ available: false, busy: false });
    controller.absarPrintOrm = useService("orm");
    controller.absarPrintAction = useService("action");
    onWillStart(async () => {
        if (controller.env.inDialog || !controller.props.resModel) return;
        const reports = await controller.absarPrintOrm.call(
            "absar.print.wizard", "available_reports", [controller.props.resModel, viewType]
        );
        controller.absarPrint.available = reports.length > 0;
    });
}
async function openPrint(controller, ids, viewType) {
    if (!ids.length) return;
    const action = await controller.absarPrintOrm.call(
        "absar.print.wizard", "open_for_records", [controller.props.resModel, ids, viewType],
        { context: controller.props.context }
    );
    await controller.absarPrintAction.doAction(action);
}
patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        setupPrint(this, "form");
        useSubEnv({ absarDirectPrint: {
            state: this.absarPrint,
            canPrint: () => this.absarPrint.available && Boolean(this.model.root.resId) && !this.env.inDialog,
            open: () => this.absarOpenPrint(),
        } });
    },
    async absarOpenPrint() {
        if (this.absarPrint.busy) return;
        this.absarPrint.busy = true;
        try {
            if (!(await this.save())) return;
            if (this.model.root.resId) await openPrint(this, [this.model.root.resId], "form");
        } finally {
            this.absarPrint.busy = false;
        }
    },
});
patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        setupPrint(this, "list");
    },
    async absarOpenPrint() {
        if (this.absarPrint.busy) return;
        this.absarPrint.busy = true;
        try {
            if (this.editedRecord && !(await this.editedRecord.save())) return;
            await openPrint(this, await this.getSelectedResIds(), "list");
        } finally {
            this.absarPrint.busy = false;
        }
    },
});

// Forms without a workflow header get the same document-action row.
// Existing headers and their buttons are left in their original order.
patch(FormCompiler.prototype, {
    compileForm(el, params) {
        const form = super.compileForm(...arguments);
        if (!Array.from(el.children).some((child) => child.tagName.toLowerCase() === "header")) {
            const row = createElement("div", {
                class: "o_form_statusbar mb-2",
                "t-if": "__comp__.env.absarDirectPrint and __comp__.env.absarDirectPrint.canPrint()",
            });
            row.appendChild(createElement("StatusBarButtons"));
            (form.querySelector(".o_form_sheet_bg") || form).prepend(row);
        }
        return form;
    },
});
