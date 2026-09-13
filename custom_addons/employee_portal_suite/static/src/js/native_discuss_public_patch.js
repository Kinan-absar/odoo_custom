/** @odoo-module **/

import { Discuss } from "@mail/core/public_web/discuss";
import { DiscussClientAction } from "@mail/core/public_web/discuss_client_action";
import { MessagingMenu } from "@mail/core/public_web/messaging_menu";
import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { onMounted, onWillUnmount } from "@odoo/owl";

function employeePortalMeta(name) {
    return document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") || "";
}

function epEscape(text) {
    return String(text ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
}

function epFindDirectMessagesLabel(root) {
    const nodes = root.querySelectorAll("span, div, button, h1, h2, h3, h4, h5, h6");
    for (const node of nodes) {
        const ownText = Array.from(node.childNodes)
            .filter((n) => n.nodeType === Node.TEXT_NODE)
            .map((n) => n.textContent || "")
            .join(" ")
            .trim()
            .replace(/\s+/g, " ")
            .toLowerCase();
        if (ownText === "direct messages") return node;
    }
    return null;
}


function epFindChannelsLabel(root) {
    const nodes = root.querySelectorAll("span, div, button, h1, h2, h3, h4, h5, h6");
    for (const node of nodes) {
        const ownText = Array.from(node.childNodes)
            .filter((n) => n.nodeType === Node.TEXT_NODE)
            .map((n) => n.textContent || "")
            .join(" ")
            .trim()
            .replace(/\s+/g, " ")
            .toLowerCase();
        if (ownText === "channels") return node;
    }
    return null;
}

function epHideNativeChannelsSection(root) {
    const label = epFindChannelsLabel(root);
    if (!label) return;
    // Odoo's sidebar section wrapper is the nearest block that owns the heading.
    // Prefer a semantic section, then fall back to the immediate parent.
    const section = label.closest("section, .o-mail-DiscussSidebar-category, .o-mail-DiscussSidebar-section") || label.parentElement;
    if (section) section.classList.add("ep-native-hidden-channels-section");
}

function epBuildNewChatModal() {
    let modal = document.getElementById("ep-native-new-chat-modal");
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "ep-native-new-chat-modal";
    modal.className = "ep-native-new-chat-modal";
    modal.innerHTML = `
      <div class="ep-native-new-chat-backdrop" data-ep-close-new-chat="1"></div>
      <div class="ep-native-new-chat-dialog" role="dialog" aria-modal="true" aria-label="New chat">
        <div class="ep-native-new-chat-head">
          <div><strong>New chat</strong><small>Choose an employee or create a group</small></div>
          <button type="button" class="ep-native-icon-btn" data-ep-close-new-chat="1" aria-label="Close">&times;</button>
        </div>
        <div class="ep-native-new-chat-search-wrap">
          <i class="fa fa-search"></i>
          <input type="search" placeholder="Search employees" data-ep-new-chat-search="1" autocomplete="off"/>
        </div>
        <div class="ep-native-new-chat-people" data-ep-new-chat-people="1"><div class="ep-native-new-chat-loading">Loading employees…</div></div>
        <div class="ep-native-new-chat-footer">
          <input type="text" class="form-control ep-native-group-name" placeholder="Group name (optional)" data-ep-new-chat-group-name="1"/>
          <button type="button" class="btn btn-primary" data-ep-start-new-chat="1" disabled>Start chat</button>
        </div>
      </div>`;
    document.body.appendChild(modal);

    const close = () => modal.classList.remove("show");
    modal.querySelectorAll("[data-ep-close-new-chat]").forEach((el) => el.addEventListener("click", close));
    modal.addEventListener("keydown", (ev) => { if (ev.key === "Escape") close(); });
    modal.querySelector("[data-ep-new-chat-search]")?.addEventListener("input", (ev) => {
        const q = (ev.target.value || "").trim().toLowerCase();
        modal.querySelectorAll("[data-ep-person-row]").forEach((row) => {
            row.classList.toggle("d-none", q && !(row.dataset.name || "").includes(q));
        });
    });
    modal.querySelector("[data-ep-start-new-chat]")?.addEventListener("click", async (ev) => {
        const button = ev.currentTarget;
        const ids = Array.from(modal.querySelectorAll("input[data-ep-person-check]:checked")).map((el) => Number(el.value));
        if (!ids.length) return;
        button.disabled = true;
        const old = button.textContent;
        button.textContent = "Opening…";
        try {
            const result = await rpc("/employee_portal/discuss/start_json", {
                user_ids: ids,
                group_name: modal.querySelector("[data-ep-new-chat-group-name]")?.value || "",
            });
            if (!result?.ok || !result?.url) throw new Error(result?.error || "Unable to start chat.");
            window.location.assign(result.url);
        } catch (error) {
            console.error("Unable to start employee chat", error);
            window.alert(error?.message || "Unable to start chat.");
            button.disabled = false;
            button.textContent = old;
        }
    });
    return modal;
}

async function epOpenNewChat() {
    const modal = epBuildNewChatModal();
    modal.classList.add("show");
    const peopleBox = modal.querySelector("[data-ep-new-chat-people]");
    peopleBox.innerHTML = '<div class="ep-native-new-chat-loading">Loading employees…</div>';
    try {
        const result = await rpc("/employee_portal/discuss/people_all", {});
        const people = result?.people || [];
        peopleBox.innerHTML = people.length ? people.map((person) => `
          <label class="ep-native-person-row" data-ep-person-row="1" data-name="${epEscape((person.name || '').toLowerCase())}">
            <input type="checkbox" data-ep-person-check="1" value="${Number(person.id)}"/>
            ${person.avatar ? `<img src="${person.avatar}" alt=""/>` : '<span class="ep-native-person-avatar-fallback"><i class="fa fa-user"></i></span>'}
            <span class="ep-native-person-text"><strong>${epEscape(person.name)}</strong><small class="ep-native-person-presence ${epEscape(person.presence || 'offline')}"><span></span>${epEscape(person.presence_label || 'Offline')}</small></span>
          </label>`).join("") : '<div class="ep-native-new-chat-loading">No other employees found.</div>';
        const update = () => {
            const checked = peopleBox.querySelectorAll("input[data-ep-person-check]:checked").length;
            const start = modal.querySelector("[data-ep-start-new-chat]");
            if (start) start.disabled = checked === 0;
            const groupName = modal.querySelector("[data-ep-new-chat-group-name]");
            if (groupName) groupName.style.display = checked > 1 ? "block" : "none";
        };
        peopleBox.querySelectorAll("input[data-ep-person-check]").forEach((el) => el.addEventListener("change", update));
        update();
    } catch (error) {
        console.error("Unable to load employees", error);
        peopleBox.innerHTML = '<div class="ep-native-new-chat-loading text-danger">Unable to load employees.</div>';
    }
    window.setTimeout(() => modal.querySelector("[data-ep-new-chat-search]")?.focus(), 20);
}

function epEnhanceNativeSidebar() {
    if (!employeePortalMeta("employee-portal-discuss")) return;
    const root = document.querySelector(".o-mail-Discuss") || document.body;
    epHideNativeChannelsSection(root);
    const label = epFindDirectMessagesLabel(root);
    if (!label) return;

    // Keep the native DM rows and behavior; only turn their section into the Chats hub.
    const textNode = Array.from(label.childNodes).find((n) => n.nodeType === Node.TEXT_NODE && (n.textContent || "").trim());
    if (textNode && (textNode.textContent || "").trim().toLowerCase() === "direct messages") textNode.textContent = "Chats";
    else if (label.textContent.trim().toLowerCase() === "direct messages") label.textContent = "Chats";

    // Make the Chats section title itself the permanent home shortcut.
    // This intentionally navigates to the canonical Discuss root so it works the same
    // in a normal browser tab and in the installed PWA.
    label.classList.add("ep-native-chats-home-link");
    label.setAttribute("role", "link");
    label.setAttribute("tabindex", "0");
    label.setAttribute("title", "Open Chats home");
    if (label.dataset.epChatsHomeBound !== "1") {
        label.dataset.epChatsHomeBound = "1";
        const goHome = (ev) => {
            ev?.preventDefault?.();
            ev?.stopPropagation?.();
            window.location.assign("/my/employee/discuss");
        };
        label.addEventListener("click", goHome);
        label.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter" || ev.key === " ") goHome(ev);
        });
    }

    let header = label.closest("div") || label.parentElement;
    if (!header) return;
    header.classList.add("ep-native-chats-section-head");
    if (!header.querySelector("[data-ep-new-native-chat]")) {
        const actions = document.createElement("span");
        actions.className = "ep-native-chats-section-actions";
        actions.innerHTML = `
          <button type="button" data-ep-discuss-install="1" class="ep-native-sidebar-action" title="Install Chats" aria-label="Install Chats"><i class="fa fa-download"></i></button>
          <button type="button" data-ep-new-native-chat="1" class="ep-native-sidebar-action" title="New chat" aria-label="New chat"><i class="fa fa-plus"></i></button>`;
        header.appendChild(actions);
        actions.querySelector("[data-ep-new-native-chat]")?.addEventListener("click", (ev) => { ev.preventDefault(); ev.stopPropagation(); epOpenNewChat(); });
        actions.querySelector("[data-ep-discuss-install]")?.addEventListener("click", (ev) => { ev.preventDefault(); ev.stopPropagation(); window.EmployeeDiscussPWA?.install?.(); });
    }
}

function epEnhanceConversationHeader(component) {
    if (!employeePortalMeta("employee-portal-discuss")) return;
    const root = component?.root?.el || document.querySelector(".o-mail-Discuss") || document.body;
    const header = root.querySelector(".o-mail-Discuss-header");
    if (!header) return;

    // `discuss_public_thread` is only the server bootstrap record.  The actual
    // visible conversation is `store.discuss.thread`; using the bootstrap record
    // here would make the home screen look like an open chat again.
    const hasThread = Boolean(component?.store?.discuss?.thread);
    const isMobile = window.matchMedia("(max-width: 767.98px)").matches;

    // Mobile navigation should be explicit and dependable.  The previous swipe
    // gesture has been removed; every open conversation now gets a normal back
    // button that returns to the canonical Chats/Discuss home.
    let back = header.querySelector("[data-ep-mobile-chat-back]");
    if (isMobile && hasThread) {
        if (!back) {
            back = document.createElement("button");
            back.type = "button";
            back.className = "btn btn-link ep-native-mobile-chat-back";
            back.dataset.epMobileChatBack = "1";
            back.setAttribute("aria-label", "Back to Chats");
            back.setAttribute("title", "Back to Chats");
            back.innerHTML = '<i class="fa fa-chevron-left" aria-hidden="true"></i><span>Chats</span>';
            back.addEventListener("click", (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                window.location.assign("/my/employee/discuss");
            });
            header.prepend(back);
        }
    } else {
        back?.remove();
    }

    // Add a native-RTC video action next to the existing phone call control.  We
    // deliberately do not create a second call system: EmployeePortalNativeRTC
    // is only a small bridge to Odoo's own Rtc.joinCall(..., camera:true).
    if (hasThread && !header.querySelector("[data-ep-native-video-call]")) {
        const video = document.createElement("button");
        video.type = "button";
        video.className = "btn btn-link ep-native-video-call";
        video.dataset.epNativeVideoCall = "1";
        video.setAttribute("aria-label", "Video call");
        video.setAttribute("title", "Video call");
        video.innerHTML = '<i class="fa fa-video-camera" aria-hidden="true"></i>';
        video.addEventListener("click", async (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            video.disabled = true;
            try {
                if (!window.EmployeePortalNativeRTC?.videoCall) {
                    throw new Error("Native Discuss video calling is still loading. Please try again.");
                }
                await window.EmployeePortalNativeRTC.videoCall();
            } catch (error) {
                console.error("Employee Portal: native video call failed", error);
                window.alert(error?.message || "Unable to start video call.");
            } finally {
                video.disabled = false;
            }
        });

        const phoneButton = Array.from(header.querySelectorAll("button")).find((button) => {
            if (button === video || button.matches("[data-ep-mobile-chat-back]")) return false;
            const label = `${button.getAttribute("title") || ""} ${button.getAttribute("aria-label") || ""}`.toLowerCase();
            return Boolean(button.querySelector(".fa-phone")) || /(^|\s)(audio )?call(\s|$)/.test(label);
        });
        if (phoneButton?.parentNode) {
            phoneButton.insertAdjacentElement("afterend", video);
        } else {
            header.appendChild(video);
        }
    }
}


// Keep Odoo's native MessagingMenu implementation untouched. On mobile we
// open its Chat view as the landing surface and hide only the Channel tab with
// portal-scoped CSS. Patching the component tabs itself can remove the native
// mobile Chat control on some Odoo 18 builds.

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
        // The canonical Chats home must never inherit Odoo's remembered/last-active
        // thread.  That remembered active id is exactly what caused the app to reopen
        // whichever conversation was last used.  On the home route, always bootstrap
        // from the server-provided public thread and ignore the restored client state.
        if (employeePortalMeta("employee-portal-discuss-home")) {
            const publicThread = this.store?.discuss_public_thread;
            const publicActiveId = this.store?.Thread?.localIdToActiveId?.(publicThread?.localId);
            return publicActiveId || "mail.box_inbox";
        }
        const activeId = super.getActiveId(props);
        if (activeId) {
            return activeId;
        }
        const publicThread = this.store?.discuss_public_thread;
        const publicActiveId = this.store?.Thread?.localIdToActiveId?.(publicThread?.localId);
        return publicActiveId || "mail.box_inbox";
    },

    parseActiveId(rawActiveId) {
        // Same rule as getActiveId(): the home route is independent of the last chat.
        if (employeePortalMeta("employee-portal-discuss-home") || !rawActiveId) {
            const publicThread = this.store?.discuss_public_thread;
            rawActiveId =
                this.store?.Thread?.localIdToActiveId?.(publicThread?.localId) ||
                "mail.box_inbox";
        }
        return super.parseActiveId(rawActiveId);
    },

    async restoreDiscussThread() {
        // Let Odoo fully initialise its native Discuss stores first.  Once that is
        // complete, explicitly clear the visible thread on the canonical home.  This
        // preserves the native sidebar/mobile MessagingMenu without showing a stale
        // remembered conversation.
        const result = await super.restoreDiscussThread(...arguments);
        if (employeePortalMeta("employee-portal-discuss-home") && this.store?.discuss) {
            const isMobile = window.matchMedia("(max-width: 767.98px)").matches;
            this.store.discuss.thread = undefined;
            this.store.discuss.activeTab = isMobile ? "chat" : "main";
        }
        return result;
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
            if (isEmployeePortalDiscussHome) {
                // A stable neutral home: do not expose Odoo's remembered thread.
                this.store.discuss.thread = undefined;
                this.store.discuss.activeTab = window.matchMedia("(max-width: 767.98px)").matches ? "chat" : "main";
            } else {
                if (!this.store.discuss.thread && this.store.discuss_public_thread) {
                    this.store.discuss.thread = this.store.discuss_public_thread;
                }
                this.store.discuss.activeTab = "main";
            }
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
                epEnhanceConversationHeader(this);
                this._epSidebarObserver = new MutationObserver(() => {
                    epEnhanceNativeSidebar();
                    epEnhanceConversationHeader(this);
                });
                this._epSidebarObserver.observe(this.root?.el || document.body, { childList: true, subtree: true });
                if (isEmployeePortalDiscussHome) {
                    const isMobile = window.matchMedia("(max-width: 767.98px)").matches;
                    // Clear the selected thread *after* the native Discuss component has
                    // mounted. This is late enough to keep Odoo's lifecycle intact, but
                    // early enough that the user always sees the Discuss/Chats home.
                    this.store.discuss.thread = undefined;
                    this.store.discuss.activeTab = isMobile ? "chat" : "main";
                    requestAnimationFrame(() => {
                        if (!this.store?.discuss) return;
                        this.store.discuss.thread = undefined;
                        this.store.discuss.activeTab = isMobile ? "chat" : "main";
                    });
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
