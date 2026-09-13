/** @odoo-module **/

import { Rtc } from "@mail/discuss/call/common/rtc_service";
import { patch } from "@web/core/utils/patch";

function requestedStartMode() {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get("chats_call");
    return mode === "audio" || mode === "video" ? mode : null;
}

patch(Rtc.prototype, {
    start() {
        super.start(...arguments);
        const mode = requestedStartMode();
        if (!mode) return;
        let tries = 0;
        const attempt = async () => {
            tries += 1;
            const channel = this.store?.discuss?.thread || this.store?.discuss_public_thread;
            if (!channel || this.state?.hasPendingRequest) {
                if (tries < 60) window.setTimeout(attempt, 100);
                return;
            }
            if (this.state?.channel?.eq?.(channel)) {
                return;
            }
            try {
                await this.joinCall(channel, { audio: true, camera: mode === "video" });
                const url = new URL(window.location.href);
                url.searchParams.delete("chats_call");
                window.history.replaceState({}, "", url.toString());
            } catch (error) {
                console.error("Chats: native Discuss call start failed", error);
            }
        };
        window.setTimeout(attempt, 100);
    },
});
