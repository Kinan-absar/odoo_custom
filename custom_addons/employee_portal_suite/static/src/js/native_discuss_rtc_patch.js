/** @odoo-module **/

import { Rtc } from "@mail/discuss/call/common/rtc_service";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";

function isEmployeePortalDiscuss() {
    return Boolean(document.querySelector('meta[name="employee-portal-discuss"]'));
}

function isPortalReadOnlyChannel() {
    return document.querySelector('meta[name="employee-portal-channel-readonly"]')?.content === "1";
}

function shouldAutoAnswer() {
    const params = new URLSearchParams(window.location.search);
    return isEmployeePortalDiscuss() && params.get("auto_answer") === "1";
}

function requestedVideo() {
    return new URLSearchParams(window.location.search).get("auto_video") === "1";
}

// ---------------------------------------------------------------------------
// IMPORTANT: opening a conversation must NEVER start/join an RTC call.
// ---------------------------------------------------------------------------
// Odoo's RTC service can be asked to join from more than one UI/state path. In
// an employee-portal group conversation that used to mean that merely opening
// the group could inherit an RTC state and start a conference.  Keep native
// Odoo RTC, but require a recent, explicit user action before joinCall() is
// allowed. Incoming calls answered from the portal shell are the one deliberate
// exception (auto_answer=1 is only added by the Answer button).
let explicitRtcIntentUntil = 0;

function markExplicitRtcIntent() {
    explicitRtcIntentUntil = Date.now() + 5000;
}

function isRtcActionElement(target) {
    const el = target?.closest?.("button, a, [role='button']");
    if (!el) return false;
    const label = `${el.getAttribute("aria-label") || ""} ${el.getAttribute("title") || ""} ${el.textContent || ""}`.toLowerCase();
    const html = (el.innerHTML || "").toLowerCase();
    return (
        label.includes("call") || label.includes("video") || label.includes("camera") ||
        label.includes("phone") || label.includes("answer") || label.includes("join") ||
        label.includes("accept") || html.includes("fa-phone") || html.includes("fa-video") ||
        html.includes("phone") || html.includes("video")
    );
}

function installExplicitRtcIntentGuard() {
    if (window.__employeePortalRtcIntentGuardInstalled) return;
    window.__employeePortalRtcIntentGuardInstalled = true;
    const capture = (event) => {
        if (isEmployeePortalDiscuss() && isRtcActionElement(event.target)) {
            markExplicitRtcIntent();
        }
    };
    document.addEventListener("pointerdown", capture, true);
    document.addEventListener("click", capture, true);
}

function hasExplicitRtcIntent() {
    // userActivation covers the normal native Odoo call/video button path.
    // The short intent window also covers native handlers that await something
    // before eventually calling joinCall().
    return Boolean(
        shouldAutoAnswer() ||
        Date.now() <= explicitRtcIntentUntil ||
        window.navigator?.userActivation?.isActive
    );
}

installExplicitRtcIntentGuard();

// Keep Odoo's native RTC engine. The only bridge here is network configuration:
// reuse the Employee Portal TURN/ICE settings so native Discuss calls can cross
// NAT/firewall boundaries in the same way as the previously working call stack.
patch(Rtc.prototype, {
    start() {
        super.start(...arguments);
        if (isEmployeePortalDiscuss()) {
            window.EmployeePortalNativeRTC = {
                rtc: this,
                startVideo: async () => {
                    const channel = this.store?.discuss?.thread || this.store?.discuss_public_thread;
                    if (!channel) throw new Error("Open a conversation before starting a video call.");
                    markExplicitRtcIntent();
                    return await this.joinCall(channel, { audio: true, camera: true });
                },
            };
        }
        // Expose the *native Odoo Discuss RTC service* to the employee Discuss
        // header enhancer. The video button added there therefore uses the same
        // RTC session, invitation and call UI as Odoo's own phone call button.
        window.__employeePortalNativeRtc = this;
        const startVideo = async () => {
            const channel = this.store?.discuss?.thread || this.store?.discuss_public_thread;
            if (!channel) {
                throw new Error("Open a conversation before starting a video call.");
            }
            markExplicitRtcIntent();
            return await this.joinCall(channel, { audio: true, camera: true });
        };
        window.EmployeePortalNativeRTC = {
            ...(window.EmployeePortalNativeRTC || {}),
            rtc: this,
            startVideo,
            videoCall: startVideo,
        };

        // Only the explicit Answer action from the portal shell may auto-join.
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
                markExplicitRtcIntent();
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
        if (isEmployeePortalDiscuss() && isPortalReadOnlyChannel()) {
            throw new Error("Calls are disabled for this read-only Channel.");
        }

        // Hard stop for the bug reported on portal group conversations: loading,
        // selecting or restoring a thread is not permission to start a conference.
        // A native phone/video/join/answer click (or the explicit shell Answer
        // route) is required first. This applies to DMs and groups alike so a
        // malformed/stale RTC state can never auto-open media on navigation.
        if (isEmployeePortalDiscuss() && !hasExplicitRtcIntent()) {
            console.warn("Employee Portal: blocked automatic RTC join while opening a conversation.");
            throw new Error("A call can only be started or joined after pressing the call or video button.");
        }

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
