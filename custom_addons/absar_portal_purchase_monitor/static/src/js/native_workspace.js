/** @odoo-module **/
import { Component, onMounted, useState, whenReady } from "@odoo/owl";
import { mountComponent } from "@web/env";
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
        this.action = useService("action");
        this.boot = odoo.absarPurchase;
        this.state = useState({error: null});
        useBus(routerBus, "ROUTE_CHANGE", async () => {
            await this.action.loadState();
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
                this.state.error = error.message || String(error);
                throw error;
            }
        });
    }
    async open(section) {
        await this.action.doAction(this.boot.actions[section], {clearBreadcrumbs: true});
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
        message.textContent = "Purchase could not start. " + (error.message || String(error));
        target.replaceChildren(message);
        console.error(error);
    }
});
