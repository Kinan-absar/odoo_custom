/** @odoo-module **/

import { Discuss } from "@mail/core/public_web/discuss";
import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";

function meta(name) {
    return document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") || "";
}

function isEmbeddedDiscuss() {
    return Boolean(meta("employee-portal-discuss-embedded"));
}

function isPortalConversationPage() {
    return isEmbeddedDiscuss() || /\/my\/employee\/discuss\/channel\/\d+\/?$/.test(window.location.pathname);
}

function isPortalReadOnlyChannel() {
    return meta("employee-portal-channel-readonly") === "1";
}

function isPortalGroupConversation() {
    return meta("employee-portal-channel-type") === "group" && meta("employee-portal-can-leave-group") === "1";
}

function currentPortalChannelId() {
    const match = window.location.pathname.match(/\/my\/employee\/discuss\/channel\/(\d+)/);
    return match ? Number(match[1]) : 0;
}

async function employeePortalJsonRpc(route, params = {}) {
    const response = await fetch(route, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", method: "call", params, id: Date.now() }),
    });
    const payload = await response.json();
    if (payload.error) throw new Error(payload.error.data?.message || payload.error.message || "RPC error");
    return payload.result || {};
}

function removeEmbeddedCloseButton(header) {
    if (!isPortalConversationPage()) return;
    const controls = Array.from(header.querySelectorAll("button, a"));
    for (const el of controls) {
        if (el.dataset.epChatsBack) continue;
        const label = `${el.getAttribute("title") || ""} ${el.getAttribute("aria-label") || ""}`.trim().toLowerCase();
        const html = (el.innerHTML || "").toLowerCase();
        if (label === "close" || label.includes("close conversation") || html.includes("fa-times") || html.includes("fa-close")) {
            el.style.display = "none";
            el.dataset.epHiddenClose = "1";
        }
    }
}


function tidyEmbeddedMobileHeader(header) {
    if (!isPortalConversationPage() || !window.matchMedia("(max-width: 767.98px)").matches || !header) return;
    const controls = Array.from(header.querySelectorAll("button, a"));
    for (const el of controls) {
        if (el.dataset.epChatsBack || el.dataset.epGroupActions || el.closest?.("[data-ep-group-actions]")) {
            el.style.removeProperty("display");
            continue;
        }
        const label = `${el.getAttribute("title") || ""} ${el.getAttribute("aria-label") || ""} ${el.textContent || ""}`.toLowerCase();
        const html = (el.innerHTML || "").toLowerCase();
        const classes = String(el.className || "").toLowerCase();
        // Historical extra video action must stay gone.
        if (classes.includes("ep-native-video-call")) {
            el.style.setProperty("display", "none", "important");
            continue;
        }
        // Mobile chat header: keep only Back, native audio/video call controls,
        // and the native add-participant (+) action. Everything else (search,
        // settings, bell/notifications, pin, close, overflow actions, etc.) is hidden.
        const isCall = label.includes("call") || label.includes("video") || label.includes("camera") ||
            html.includes("fa-phone") || html.includes("fa-video") || html.includes("phone") || html.includes("video");
        const isAddPeople = label.includes("add people") || label.includes("add person") ||
            label.includes("add participant") || label.includes("invite") || label.includes("member") ||
            label.includes("participant") || html.includes("user-plus") || html.includes("fa-user-plus") ||
            html.includes("plus");
        if (isCall || isAddPeople) {
            el.style.removeProperty("display");
            el.dataset.epMobileAllowedAction = "1";
        } else {
            el.style.setProperty("display", "none", "important");
            el.dataset.epMobileHiddenAction = "1";
        }
    }
}
function goBackToChats() {
    if (isEmbeddedDiscuss() && window.parent && window.parent !== window) {
        window.parent.postMessage({ type: "employee-discuss-back-to-chats" }, window.location.origin);
        return;
    }
    const backUrl = meta("employee-portal-back-url") || "/my/employee/discuss";
    try {
        const referrer = document.referrer ? new URL(document.referrer) : null;
        if (referrer && referrer.origin === window.location.origin && referrer.pathname.replace(/\/+$/, "") === backUrl.replace(/\/+$/, "")) {
            window.history.back();
            return;
        }
    } catch (_) {}
    window.location.assign(backUrl);
}

function ensurePortalGroupActions(header) {
    if (!isPortalGroupConversation() || !header || header.querySelector("[data-ep-group-actions]")) return;
    const channelId = currentPortalChannelId();
    if (!channelId) return;

    const wrap = document.createElement("div");
    wrap.className = "ep-group-actions-wrap";
    wrap.dataset.epGroupActions = "1";
    wrap.innerHTML = `
        <button type="button" class="ep-group-actions-button" data-ep-group-actions="1" title="Group options" aria-label="Group options">
            <i class="fa fa-ellipsis-v"></i>
        </button>
        <div class="ep-group-actions-menu" hidden>
            <button type="button" data-ep-leave-group="1"><i class="fa fa-sign-out"></i><span>Exit group</span></button>
            <button type="button" class="ep-group-delete-exit" data-ep-delete-exit-group="1"><i class="fa fa-trash"></i><span>Delete &amp; Exit</span></button>
        </div>`;
    const toggle = wrap.querySelector(".ep-group-actions-button");
    const menu = wrap.querySelector(".ep-group-actions-menu");
    toggle.addEventListener("click", (ev) => {
        ev.preventDefault(); ev.stopPropagation();
        menu.hidden = !menu.hidden;
    });
    const close = () => { menu.hidden = true; };
    document.addEventListener("click", close, { once: true });

    wrap.querySelector("[data-ep-leave-group]").addEventListener("click", async (ev) => {
        ev.preventDefault(); ev.stopPropagation();
        if (!window.confirm("Exit this group? The group and its messages will remain for the other members.")) return;
        try {
            const result = await employeePortalJsonRpc("/employee_portal/discuss/leave_group", { channel_id: channelId });
            if (!result.ok) throw new Error(result.error || "Unable to exit group.");
            goBackToChats();
        } catch (error) { window.alert(error.message || "Unable to exit group."); }
    });
    wrap.querySelector("[data-ep-delete-exit-group]").addEventListener("click", async (ev) => {
        ev.preventDefault(); ev.stopPropagation();
        if (!window.confirm("Delete this group from your Chats and exit it? This does NOT delete the group for the other members.")) return;
        try {
            const result = await employeePortalJsonRpc("/employee_portal/discuss/delete_exit_group", { channel_id: channelId });
            if (!result.ok) throw new Error(result.error || "Unable to delete and exit group.");
            goBackToChats();
        } catch (error) { window.alert(error.message || "Unable to delete and exit group."); }
    });
    header.appendChild(wrap);
}

function ensureEmbeddedHeaderActions() {
    if (!meta("employee-portal-discuss")) return;
    const header = document.querySelector(".o-mail-Discuss-header");
    if (!header) return;

    removeEmbeddedCloseButton(header);
    ensurePortalGroupActions(header);
    if (isPortalReadOnlyChannel()) {
        for (const el of Array.from(header.querySelectorAll("button, a"))) {
            if (!el.dataset.epChatsBack) {
                el.style.setProperty("display", "none", "important");
                el.dataset.epReadOnlyHiddenAction = "1";
            }
        }
    } else {
        tidyEmbeddedMobileHeader(header);
    }

    const isMobileChannel = window.matchMedia("(max-width: 767.98px)").matches && /\/my\/employee\/discuss\/channel\/\d+/.test(window.location.pathname);
    if ((isEmbeddedDiscuss() || isMobileChannel) && !header.querySelector("[data-ep-chats-back]")) {
        const back = document.createElement("button");
        back.type = "button";
        back.dataset.epChatsBack = "1";
        back.className = "ep-native-inline-back";
        back.title = "Back to Chats";
        back.setAttribute("aria-label", "Back to Chats");
        back.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>';
        back.addEventListener("click", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            goBackToChats();
        });
        header.insertBefore(back, header.firstElementChild || null);
    }

}

// Employee Portal Discuss is authenticated and membership is validated server-side,
// therefore keep Odoo's native attachment uploader exactly as in backend Discuss.
patch(Composer.prototype, {
    get allowUpload() {
        if (meta("employee-portal-discuss")) return !isPortalReadOnlyChannel();
        return super.allowUpload;
    },
});

patch(Discuss.prototype, {
    setup() {
        const isEmployeePortalDiscuss = Boolean(meta("employee-portal-discuss"));
        const storeService = this.env.services["mail.store"];
        const originalPublicPage = storeService?.inPublicPage;

        // This is the stable behavior that was already working before the PWA work:
        // native Odoo Discuss owns the conversation, attachments, voice notes and RTC.
        if (isEmployeePortalDiscuss && storeService) storeService.inPublicPage = false;
        super.setup(...arguments);
        if (isEmployeePortalDiscuss && storeService) {
            storeService.inPublicPage = originalPublicPage;
            if (!this.store.discuss.thread && this.store.discuss_public_thread) {
                this.store.discuss.thread = this.store.discuss_public_thread;
            }
            this.store.discuss.activeTab = "main";
            document.body.classList.add("ep-native-discuss-public");
            if (isPortalConversationPage()) {
                document.body.classList.add("ep-native-discuss-channel");
            }
            if (isPortalReadOnlyChannel()) {
                document.body.classList.add("ep-native-discuss-readonly");
            }
            if (meta("employee-portal-discuss-embedded")) {
                document.body.classList.add("ep-native-discuss-embedded");
            }
        }
        this.isEmployeePortalDiscuss = isEmployeePortalDiscuss;

        if (isEmployeePortalDiscuss) {
            const originalBodyStyle = {
                position: document.body.style.position,
                inset: document.body.style.inset,
                width: document.body.style.width,
                height: document.body.style.height,
                overflow: document.body.style.overflow,
            };
            const originalHtmlOverflow = document.documentElement.style.overflow;

            this._epApplyViewportHeight = () => {
                const viewport = window.visualViewport;
                const isMobile = window.matchMedia("(max-width: 767.98px)").matches;
                const height = Math.max(320, Math.round(viewport?.height || window.innerHeight || document.documentElement.clientHeight));
                const top = isMobile ? Math.max(0, Math.round(viewport?.offsetTop || 0)) : 0;
                document.documentElement.style.setProperty("--ep-discuss-height", `${height}px`);
                document.documentElement.style.setProperty("--ep-discuss-top", `${top}px`);
                if (isMobile) {
                    document.documentElement.style.overflow = "hidden";
                    Object.assign(document.body.style, {
                        position: "fixed", inset: "0", width: "100%", height: "100%", overflow: "hidden",
                    });
                }
                if (this.root?.el) {
                    this.root.el.style.height = `${height}px`;
                    this.root.el.style.minHeight = "0";
                    this.root.el.style.maxHeight = `${height}px`;
                }
                if (this.contentRef?.el) {
                    this.contentRef.el.style.height = "100%";
                    this.contentRef.el.style.maxHeight = "100%";
                    this.contentRef.el.style.overflow = "hidden";
                }
            };

            this._epOnFocusIn = (ev) => {
                if (!ev.target?.closest?.(".o-mail-Composer")) return;
                document.body.classList.add("ep-native-discuss-keyboard");
                window.setTimeout(this._epApplyViewportHeight, 0);
                window.setTimeout(this._epApplyViewportHeight, 120);
                window.setTimeout(this._epApplyViewportHeight, 320);
            };
            this._epOnFocusOut = (ev) => {
                if (!ev.target?.closest?.(".o-mail-Composer")) return;
                document.body.classList.remove("ep-native-discuss-keyboard");
                window.setTimeout(this._epApplyViewportHeight, 80);
                window.setTimeout(this._epApplyViewportHeight, 300);
            };

            // Mobile back navigation is intentionally left to the browser/PWA history.
            // Do not install custom touch/pointer swipe handlers here; Safari already
            // provides its native history gesture when the conversation is a top-level page.

            onMounted(() => {
                ensureEmbeddedHeaderActions();
                this._epHeaderObserver = new MutationObserver(ensureEmbeddedHeaderActions);
                this._epHeaderObserver.observe(this.root?.el || document.body, { childList: true, subtree: true });
                this._epApplyViewportHeight();
                window.setTimeout(this._epApplyViewportHeight, 80);
                window.setTimeout(this._epApplyViewportHeight, 300);
                window.visualViewport?.addEventListener("resize", this._epApplyViewportHeight);
                window.visualViewport?.addEventListener("scroll", this._epApplyViewportHeight);
                window.addEventListener("orientationchange", this._epApplyViewportHeight);
                document.addEventListener("focusin", this._epOnFocusIn, true);
                document.addEventListener("focusout", this._epOnFocusOut, true);
            });
            onWillUnmount(() => {
                this._epHeaderObserver?.disconnect();
                window.visualViewport?.removeEventListener("resize", this._epApplyViewportHeight);
                window.visualViewport?.removeEventListener("scroll", this._epApplyViewportHeight);
                window.removeEventListener("orientationchange", this._epApplyViewportHeight);
                document.removeEventListener("focusin", this._epOnFocusIn, true);
                document.removeEventListener("focusout", this._epOnFocusOut, true);
                document.documentElement.style.removeProperty("--ep-discuss-height");
                document.documentElement.style.removeProperty("--ep-discuss-top");
                document.documentElement.style.overflow = originalHtmlOverflow;
                Object.assign(document.body.style, originalBodyStyle);
                document.body.classList.remove("ep-native-discuss-keyboard", "ep-native-discuss-public", "ep-native-discuss-embedded", "ep-native-discuss-channel", "ep-native-discuss-readonly");
            });
        }
    },
});
