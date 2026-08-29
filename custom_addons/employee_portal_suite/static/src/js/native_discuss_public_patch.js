/** @odoo-module **/

import { Discuss } from "@mail/core/public_web/discuss";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";

function employeePortalMeta(name) {
    return document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") || "";
}

patch(Discuss.prototype, {
    setup() {
        const isEmployeePortalDiscuss = Boolean(employeePortalMeta("employee-portal-discuss"));
        const storeService = this.env.services["mail.store"];
        const originalPublicPage = storeService?.inPublicPage;

        // Make the selected conversation the main thread, like backend Discuss,
        // rather than opening a second compact ChatWindow on mobile.
        if (isEmployeePortalDiscuss && storeService) {
            storeService.inPublicPage = false;
        }
        super.setup(...arguments);
        if (isEmployeePortalDiscuss && storeService) {
            storeService.inPublicPage = originalPublicPage;
            if (!this.store.discuss.thread && this.store.discuss_public_thread) {
                this.store.discuss.thread = this.store.discuss_public_thread;
            }
            this.store.discuss.activeTab = "main";
            document.body.classList.add("ep-native-discuss-public");
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
                const height = Math.max(
                    320,
                    Math.round(viewport?.height || window.innerHeight || document.documentElement.clientHeight)
                );
                const top = isMobile ? Math.max(0, Math.round(viewport?.offsetTop || 0)) : 0;
                document.documentElement.style.setProperty("--ep-discuss-height", `${height}px`);
                document.documentElement.style.setProperty("--ep-discuss-top", `${top}px`);

                if (isMobile) {
                    // iOS Safari otherwise scrolls the whole document to reveal the
                    // focused contenteditable. Fix the app shell to the visual viewport;
                    // only the native message thread is allowed to scroll.
                    document.documentElement.style.overflow = "hidden";
                    Object.assign(document.body.style, {
                        position: "fixed",
                        inset: "0",
                        width: "100%",
                        height: "100%",
                        overflow: "hidden",
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
                window.visualViewport?.removeEventListener("resize", this._epApplyViewportHeight);
                window.visualViewport?.removeEventListener("scroll", this._epApplyViewportHeight);
                window.removeEventListener("orientationchange", this._epApplyViewportHeight);
                document.removeEventListener("focusin", this._epOnFocusIn, true);
                document.removeEventListener("focusout", this._epOnFocusOut, true);
                document.documentElement.style.removeProperty("--ep-discuss-height");
                document.documentElement.style.removeProperty("--ep-discuss-top");
                document.documentElement.style.overflow = originalHtmlOverflow;
                Object.assign(document.body.style, originalBodyStyle);
                document.body.classList.remove("ep-native-discuss-keyboard");
                document.body.classList.remove("ep-native-discuss-public");
            });
        }
    },

    goEmployeeMessages() {
        window.location.href = employeePortalMeta("employee-portal-back-url") || "/my/employee/discuss";
    },

    goEmployeePortal() {
        window.location.href = employeePortalMeta("employee-portal-home-url") || "/my/employee";
    },

    async toggleEmployeeFullscreen() {
        try {
            if (!document.fullscreenElement) {
                await document.documentElement.requestFullscreen?.();
            } else {
                await document.exitFullscreen?.();
            }
        } catch (_) {
            // Fullscreen is optional.
        }
    },
});
