/** @odoo-module **/

import { Discuss } from "@mail/core/public_web/discuss";
import { DiscussClientAction } from "@mail/core/public_web/discuss_client_action";
import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { onMounted, onWillUnmount } from "@odoo/owl";

function employeePortalMeta(name) {
    return document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") || "";
}
\nfunction epEscape(text) {\n    return String(text ?? \"\").replace(/[&<>\"']/g, (ch) => ({\n        \"&\": \"&amp;\", \"<\": \"&lt;\", \">\": \"&gt;\", '\"': \"&quot;\", \"'\": \"&#39;\",\n    }[ch]));\n}\n\nfunction epFindDirectMessagesLabel(root) {\n    const nodes = root.querySelectorAll(\"span, div, button, h1, h2, h3, h4, h5, h6\");\n    for (const node of nodes) {\n        const ownText = Array.from(node.childNodes)\n            .filter((n) => n.nodeType === Node.TEXT_NODE)\n            .map((n) => n.textContent || \"\")\n            .join(\" \")\n            .trim()\n            .replace(/\\s+/g, \" \")\n            .toLowerCase();\n        if (ownText === \"direct messages\") return node;\n    }\n    return null;\n}\n\nfunction epBuildNewChatModal() {\n    let modal = document.getElementById(\"ep-native-new-chat-modal\");\n    if (modal) return modal;\n    modal = document.createElement(\"div\");\n    modal.id = \"ep-native-new-chat-modal\";\n    modal.className = \"ep-native-new-chat-modal\";\n    modal.innerHTML = `\n      <div class=\"ep-native-new-chat-backdrop\" data-ep-close-new-chat=\"1\"></div>\n      <div class=\"ep-native-new-chat-dialog\" role=\"dialog\" aria-modal=\"true\" aria-label=\"New chat\">\n        <div class=\"ep-native-new-chat-head\">\n          <div><strong>New chat</strong><small>Choose an employee or create a group</small></div>\n          <button type=\"button\" class=\"ep-native-icon-btn\" data-ep-close-new-chat=\"1\" aria-label=\"Close\">&times;</button>\n        </div>\n        <div class=\"ep-native-new-chat-search-wrap\">\n          <i class=\"fa fa-search\"></i>\n          <input type=\"search\" placeholder=\"Search employees\" data-ep-new-chat-search=\"1\" autocomplete=\"off\"/>\n        </div>\n        <div class=\"ep-native-new-chat-people\" data-ep-new-chat-people=\"1\"><div class=\"ep-native-new-chat-loading\">Loading employees…</div></div>\n        <div class=\"ep-native-new-chat-footer\">\n          <input type=\"text\" class=\"form-control ep-native-group-name\" placeholder=\"Group name (optional)\" data-ep-new-chat-group-name=\"1\"/>\n          <button type=\"button\" class=\"btn btn-primary\" data-ep-start-new-chat=\"1\" disabled>Start chat</button>\n        </div>\n      </div>`;\n    document.body.appendChild(modal);\n\n    const close = () => modal.classList.remove(\"show\");\n    modal.querySelectorAll(\"[data-ep-close-new-chat]\").forEach((el) => el.addEventListener(\"click\", close));\n    modal.addEventListener(\"keydown\", (ev) => { if (ev.key === \"Escape\") close(); });\n    modal.querySelector(\"[data-ep-new-chat-search]\")?.addEventListener(\"input\", (ev) => {\n        const q = (ev.target.value || \"\").trim().toLowerCase();\n        modal.querySelectorAll(\"[data-ep-person-row]\").forEach((row) => {\n            row.classList.toggle(\"d-none\", q && !(row.dataset.name || \"\").includes(q));\n        });\n    });\n    modal.querySelector(\"[data-ep-start-new-chat]\")?.addEventListener(\"click\", async (ev) => {\n        const button = ev.currentTarget;\n        const ids = Array.from(modal.querySelectorAll(\"input[data-ep-person-check]:checked\")).map((el) => Number(el.value));\n        if (!ids.length) return;\n        button.disabled = true;\n        const old = button.textContent;\n        button.textContent = \"Opening…\";\n        try {\n            const result = await rpc(\"/employee_portal/discuss/start_json\", {\n                user_ids: ids,\n                group_name: modal.querySelector(\"[data-ep-new-chat-group-name]\")?.value || \"\",\n            });\n            if (!result?.ok || !result?.url) throw new Error(result?.error || \"Unable to start chat.\");\n            window.location.assign(result.url);\n        } catch (error) {\n            console.error(\"Unable to start employee chat\", error);\n            window.alert(error?.message || \"Unable to start chat.\");\n            button.disabled = false;\n            button.textContent = old;\n        }\n    });\n    return modal;\n}\n\nasync function epOpenNewChat() {\n    const modal = epBuildNewChatModal();\n    modal.classList.add(\"show\");\n    const peopleBox = modal.querySelector(\"[data-ep-new-chat-people]\");\n    peopleBox.innerHTML = '<div class=\"ep-native-new-chat-loading\">Loading employees…</div>';
    try {\n        const result = await rpc(\"/employee_portal/discuss/people_all\", {});\n        const people = result?.people || [];\n        peopleBox.innerHTML = people.length ? people.map((person) => `\n          <label class=\"ep-native-person-row\" data-ep-person-row=\"1\" data-name=\"${epEscape((person.name || '').toLowerCase())}\">\n            <input type=\"checkbox\" data-ep-person-check=\"1\" value=\"${Number(person.id)}\"/>\n            ${person.avatar ? `<img src=\"${person.avatar}\" alt=\"\"/>` : '<span class=\"ep-native-person-avatar-fallback\"><i class=\"fa fa-user\"></i></span>'}\n            <span class=\"ep-native-person-text\"><strong>${epEscape(person.name)}</strong><small class=\"ep-native-person-presence ${epEscape(person.presence || 'offline')}\"><span></span>${epEscape(person.presence_label || 'Offline')}</small></span>\n          </label>`).join(\"\") : '<div class=\"ep-native-new-chat-loading\">No other employees found.</div>';\n        const update = () => {\n            const checked = peopleBox.querySelectorAll(\"input[data-ep-person-check]:checked\").length;\n            const start = modal.querySelector(\"[data-ep-start-new-chat]\");\n            if (start) start.disabled = checked === 0;\n            const groupName = modal.querySelector(\"[data-ep-new-chat-group-name]\");\n            if (groupName) groupName.style.display = checked > 1 ? \"block\" : \"none\";\n        };\n        peopleBox.querySelectorAll(\"input[data-ep-person-check]\").forEach((el) => el.addEventListener(\"change\", update));\n        update();\n    } catch (error) {\n        console.error(\"Unable to load employees\", error);\n        peopleBox.innerHTML = '<div class=\"ep-native-new-chat-loading text-danger\">Unable to load employees.</div>';\n    }\n    window.setTimeout(() => modal.querySelector(\"[data-ep-new-chat-search]\")?.focus(), 20);\n}\n\nfunction epEnhanceNativeSidebar() {\n    if (!employeePortalMeta(\"employee-portal-discuss\")) return;\n    const root = document.querySelector(\".o-mail-Discuss\") || document.body;\n    const label = epFindDirectMessagesLabel(root);\n    if (!label) return;\n\n    // Keep the native DM rows and behavior; only turn their section into the Chats hub.\n    const textNode = Array.from(label.childNodes).find((n) => n.nodeType === Node.TEXT_NODE && (n.textContent || \"\").trim());\n    if (textNode && (textNode.textContent || \"\").trim().toLowerCase() === \"direct messages\") textNode.textContent = \"Chats\";\n    else if (label.textContent.trim().toLowerCase() === \"direct messages\") label.textContent = \"Chats\";\n\n    let header = label.closest(\"div\") || label.parentElement;\n    if (!header) return;\n    header.classList.add(\"ep-native-chats-section-head\");\n    if (!header.querySelector(\"[data-ep-new-native-chat]\")) {\n        const actions = document.createElement(\"span\");\n        actions.className = \"ep-native-chats-section-actions\";\n        actions.innerHTML = `\n          <button type=\"button\" data-ep-discuss-install=\"1\" class=\"ep-native-sidebar-action\" title=\"Install Chats\" aria-label=\"Install Chats\"><i class=\"fa fa-download\"></i></button>\n          <button type=\"button\" data-ep-new-native-chat=\"1\" class=\"ep-native-sidebar-action\" title=\"New chat\" aria-label=\"New chat\"><i class=\"fa fa-plus\"></i></button>`;\n        header.appendChild(actions);\n        actions.querySelector(\"[data-ep-new-native-chat]\")?.addEventListener(\"click\", (ev) => { ev.preventDefault(); ev.stopPropagation(); epOpenNewChat(); });\n        actions.querySelector(\"[data-ep-discuss-install]\")?.addEventListener(\"click\", (ev) => { ev.preventDefault(); ev.stopPropagation(); window.EmployeeDiscussPWA?.install?.(); });\n    }\n}\n

// Odoo public Discuss disables some composer capabilities for generic public/guest pages.
// Employee Portal Discuss is authenticated and channel membership is validated server-side,
// so keep the native attachment uploader available here as it is in backend Discuss.
patch(Composer.prototype, {
    get allowUpload() {
        if (employeePortalMeta("employee-portal-discuss")) {
            return true;
        }
        return super.allowUpload;
    },
});


// Odoo 18 DiscussClientAction restores the current thread before the Discuss child
// component mounts.  On the neutral employee home route we must therefore keep a
// valid bootstrap thread until restoreDiscussThread() has completed.  A null active
// id makes Odoo's native parseActiveId() call .split() on null.  Guard that edge case
// using the public bootstrap thread, then the Discuss patch below clears the selected
// thread after mount so the user still lands on a neutral Chats home.
patch(DiscussClientAction.prototype, {
    getActiveId(props) {
        const activeId = super.getActiveId(props);
        if (activeId) {
            return activeId;
        }
        const publicThread = this.store?.discuss_public_thread;
        const publicActiveId = this.store?.Thread?.localIdToActiveId?.(publicThread?.localId);
        return publicActiveId || "mail.box_inbox";
    },

    parseActiveId(rawActiveId) {
        if (!rawActiveId) {
            const publicThread = this.store?.discuss_public_thread;
            rawActiveId =
                this.store?.Thread?.localIdToActiveId?.(publicThread?.localId) ||
                "mail.box_inbox";
        }
        return super.parseActiveId(rawActiveId);
    },
});

patch(Discuss.prototype, {
    setup() {
        const isEmployeePortalDiscuss = Boolean(employeePortalMeta("employee-portal-discuss"));
        const isEmployeePortalDiscussHome = Boolean(employeePortalMeta("employee-portal-discuss-home"));
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
            document.body.classList.toggle("ep-native-discuss-home", isEmployeePortalDiscussHome);
        }

        this.isEmployeePortalDiscuss = isEmployeePortalDiscuss;
        this.isEmployeePortalDiscussHome = isEmployeePortalDiscussHome;

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
                const companyLogo = employeePortalMeta("employee-discuss-company-logo");
                if (companyLogo) {
                    document.querySelectorAll("[data-ep-company-logo]").forEach((img) => {
                        img.src = companyLogo;
                    });
                }
                epEnhanceNativeSidebar();
                this._epSidebarObserver = new MutationObserver(() => epEnhanceNativeSidebar());
                this._epSidebarObserver.observe(this.root?.el || document.body, { childList: true, subtree: true });
                if (isEmployeePortalDiscussHome) {
                    // Some Odoo Discuss restore logic runs after setup.  Clear the
                    // bootstrap thread once more after mount, only on the neutral
                    // home route.  A user selection afterwards is left untouched.
                    this.store.discuss.thread = undefined;
                }
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
                this._epSidebarObserver?.disconnect();
                document.documentElement.style.removeProperty("--ep-discuss-height");
                document.documentElement.style.removeProperty("--ep-discuss-top");
                document.documentElement.style.overflow = originalHtmlOverflow;
                Object.assign(document.body.style, originalBodyStyle);
                document.body.classList.remove("ep-native-discuss-keyboard");
                document.body.classList.remove("ep-native-discuss-public");
                document.body.classList.remove("ep-native-discuss-home");
            });
        }
    },

    goEmployeeMessages() {
        window.location.href = employeePortalMeta("employee-portal-back-url") || "/my/employee/discuss";
    },

    goEmployeePortal() {
        window.location.href = employeePortalMeta("employee-portal-home-url") || "/my/employee";
    },

    installEmployeeChats() {
        if (window.EmployeeDiscussPWA?.install) {
            window.EmployeeDiscussPWA.install();
        }
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
