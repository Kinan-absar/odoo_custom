/** @odoo-module **/

import { Discuss } from "@mail/core/public_web/discuss";
import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";

function meta(name) {
    return document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") || "";
}

function isEmbedded() {
    return Boolean(meta("employee-portal-discuss-embedded"));
}

function ensureVideoButton() {
    if (!meta("employee-portal-discuss")) return;
    const header = document.querySelector(".o-mail-Discuss-header");
    if (!header || header.querySelector("[data-ep-video-call]")) return;
    const actions = header.querySelector(".o-mail-Discuss-headerActions, .o-mail-Discuss-headerActionsContainer, .o-mail-Discuss-header") || header;
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.epVideoCall = "1";
    // Keep in sync with .ep-native-video-call in native_discuss_public_patch.css
    button.className = "ep-native-video-call";
    button.title = "Video call";
    button.setAttribute("aria-label", "Video call");
    button.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14"/><rect x="3" y="6" width="12" height="12" rx="2"/></svg><span class="visually-hidden">Video call</span>';
    button.addEventListener("click", async (ev) => {
        ev.preventDefault();
        try {
            if (!window.EmployeePortalNativeRTC?.startVideo) {
                throw new Error("Call service is not ready yet.");
            }
            await window.EmployeePortalNativeRTC.startVideo();
        } catch (error) {
            console.error("Employee Portal video call failed", error);
            window.alert(error?.message || "Unable to start video call.");
        }
    });
    actions.insertBefore(button, actions.firstChild);
}

// On a direct/standalone channel link (not opened inside the Chats shell
// iframe) there is otherwise no way back to the Chats list on mobile once
// the native Discuss sidebar is scrolled out of view. Restore that path
// using the back-url the server already exposes via meta tag.
function ensureBackButton() {
    if (!meta("employee-portal-discuss") || isEmbedded()) return;
    const backUrl = meta("employee-portal-back-url");
    if (!backUrl) return;
    const header = document.querySelector(".o-mail-Discuss-header");
    if (!header || header.querySelector("[data-ep-back]")) return;
    const actions = header.querySelector(".o-mail-Discuss-headerActions, .o-mail-Discuss-headerActionsContainer, .o-mail-Discuss-header") || header;
    const link = document.createElement("a");
    link.href = backUrl;
    link.dataset.epBack = "1";
    // Keep in sync with .ep-native-mobile-chat-back in native_discuss_public_patch.css
    link.className = "ep-native-mobile-chat-back";
    link.title = "Back to Chats";
    link.setAttribute("aria-label", "Back to Chats");
    link.innerHTML = '<i class="fa fa-chevron-left" aria-hidden="true"></i><span>Chats</span>';
    actions.insertBefore(link, actions.firstChild);
}

function ensureHeaderButtons() {
    ensureBackButton();
    ensureVideoButton();
}

// Employee Portal Discuss is authenticated and membership is validated server-side,
// therefore keep Odoo's native attachment uploader exactly as in backend Discuss.
patch(Composer.prototype, {
    get allowUpload() {
        if (meta("employee-portal-discuss")) return true;
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

            onMounted(() => {
                ensureHeaderButtons();
                this._epHeaderObserver = new MutationObserver(ensureHeaderButtons);
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
                document.body.classList.remove("ep-native-discuss-keyboard", "ep-native-discuss-public", "ep-native-discuss-embedded");
            });
        }
    },
});
