/** @odoo-module **/

import { Rtc } from "@mail/discuss/call/common/rtc_service";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";

function isEmployeePortalDiscuss() {
    return Boolean(document.querySelector('meta[name="employee-portal-discuss"]'));
}


function shouldAutoAnswer() {
    const params = new URLSearchParams(window.location.search);
    return isEmployeePortalDiscuss() && params.get("auto_answer") === "1";
}

function requestedVideo() {
    return new URLSearchParams(window.location.search).get("auto_video") === "1";
}

// Keep Odoo's native RTC engine. The only bridge here is network configuration:
// reuse the Employee Portal TURN/ICE settings so native Discuss calls can cross
// NAT/firewall boundaries in the same way as the previously working call stack.
patch(Rtc.prototype, {
    start() {
        super.start(...arguments);
        if (!shouldAutoAnswer()) {
            return;
        }
        let tries = 0;
        const attempt = async () => {
            tries += 1;
            const channel = this.store?.discuss?.thread || this.store?.discuss_public_thread;
            if (!channel || this.state?.hasPendingRequest) {
                if (tries < 40) {
                    window.setTimeout(attempt, 100);
                }
                return;
            }
            if (this.state?.channel?.eq?.(channel)) {
                return;
            }
            try {
                await this.joinCall(channel, { audio: true, camera: requestedVideo() });
                const url = new URL(window.location.href);
                url.searchParams.delete("auto_answer");
                url.searchParams.delete("auto_video");
                window.history.replaceState({}, "", url.toString());
            } catch (error) {
                console.warn("Employee Portal: native auto-answer failed", error);
            }
        };
        window.setTimeout(attempt, 100);
    },

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
