/** @odoo-module **/

import { Rtc } from "@mail/discuss/call/common/rtc_service";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";

function isEmployeePortalDiscuss() {
    return Boolean(document.querySelector('meta[name="employee-portal-discuss"]'));
}

// Keep Odoo's native RTC engine. The only bridge here is network configuration:
// reuse the Employee Portal TURN/ICE settings so native Discuss calls can cross
// NAT/firewall boundaries in the same way as the previously working call stack.
patch(Rtc.prototype, {
    async joinCall(channel, options = {}) {
        if (isEmployeePortalDiscuss()) {
            try {
                const result = await rpc("/employee_portal/call/ice_servers", {});
                if (Array.isArray(result?.iceServers) && result.iceServers.length) {
                    this.iceServers = result.iceServers;
                }
            } catch (_) {
                // Native Discuss has its own STUN defaults; never block the call.
            }
        }
        return await super.joinCall(channel, options);
    },
});
