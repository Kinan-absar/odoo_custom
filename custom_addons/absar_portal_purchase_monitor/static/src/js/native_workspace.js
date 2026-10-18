/** @odoo-module **/
import { Component, onMounted, useState, whenReady } from "@odoo/owl";
import { mountComponent } from "@web/env";
import { useOwnDebugContext } from "@web/core/debug/debug_context";
import { describePurchaseError } from "./native_errors";
import { ActionContainer } from "@web/webclient/actions/action_container";
import { MainComponentsContainer } from "@web/core/main_components_container";
import { useBus, useService } from "@web/core/utils/hooks";
import { router, routerBus, startRouter } from "@web/core/browser/router";

// Odoo expressly supports adapting these conversions for a custom webclient.
// Keep native action history in this portal host, including after refresh.
const prefix = "/my/employee/purchase/app";
const nativeToUrl = router.stateToUrl;
const nativeFromUrl = router.urlToState;
router.stateToUrl = (state) => nativeToUrl(state).replace(/^\/odoo(?=\/|\?|$)/, prefix);
router.urlToState = (url) => {
    const mapped = new URL(url.href);
    if (mapped.pathname === prefix || mapped.pathname.startsWith(prefix + "/")) {
        mapped.pathname = mapped.pathname.replace(prefix, "/odoo");
    } else {
        mapped.pathname = "/odoo";
    }
    return nativeFromUrl(mapped);
};
startRouter();

class NativePurchaseWorkspace extends Component {
    static template = "absar_portal_purchase_monitor.NativeWorkspace";
    static components = { ActionContainer, MainComponentsContainer };
    static props = {};
    setup() {
        // Same root environment initialization as Odoo's WebClient. Native
        // views call useDebugCategory when developer mode is active.
        useOwnDebugContext({ categories: ["default"] });
        this.action = useService("action");
        this.boot = odoo.absarPurchase;
        this.state = useState({error: null, errorDetails: null});
        useBus(routerBus, "ROUTE_CHANGE", async () => {
            await this.runAction(() => this.action.loadState());
        });
        onMounted(async () => {
            try {
                if (router.current.action) {
                    await this.action.loadState();
                } else {
                    await this.action.doAction(this.boot.action);
                }
                this.env.bus.trigger("WEB_CLIENT_READY");
            } catch (error) {
                this.showError(error);
            }
        });
    }
    showError(error) {
        const info = describePurchaseError(error);
        this.state.error = info.message;
        this.state.errorDetails = info.details;
        console.error(error);
        if (info.details) console.error(info.details);
    }
    async runAction(callback) {
        this.state.error = null;
        this.state.errorDetails = null;
        try {
            return await callback();
        } catch (error) {
            this.showError(error);
        }
    }
    async open(section) {
        await this.runAction(() => this.action.doAction(this.boot.actions[section], {clearBreadcrumbs: true}));
    }
}
whenReady(async () => {
    const target = document.getElementById("absar-native-purchase-root");
    if (!target) return;
    target.replaceChildren();
    try {
        await mountComponent(NativePurchaseWorkspace, target);
    } catch (error) {
        const message = document.createElement("div");
        message.className = "alert alert-danger m-4";
        const info = describePurchaseError(error);
        message.textContent = "Purchase could not start. " + info.message;
        if (info.details) {
            const details = document.createElement("details");
            const summary = document.createElement("summary");
            summary.textContent = "Technical details";
            const text = document.createElement("pre");
            text.textContent = info.details;
            details.append(summary, text);
            message.append(details);
        }
        target.replaceChildren(message);
        console.error(error);
    }
});
