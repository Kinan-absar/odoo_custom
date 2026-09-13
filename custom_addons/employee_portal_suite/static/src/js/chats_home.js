/** @odoo-module **/

// Stable Chats home interactions. This file is loaded directly by the Chats home
// template as well as through web.assets_frontend, so Search / New chat / frame
// navigation do not depend on an earlier cached bundle.
(() => {
    "use strict";

    const SELECTORS = {
        shell: "[data-ep-chats-shell]",
        search: "[data-ep-chat-search]",
        thread: "[data-ep-thread]",
        newChat: "[data-ep-new-chat-toggle]",
        closeNewChat: "[data-ep-new-chat-close]",
        modal: "#ep-native-new-chat",
        frame: "[data-ep-discuss-frame]",
        empty: "[data-ep-chat-empty]",
    };

    function filterChats(input) {
        const shell = input.closest(SELECTORS.shell) || document;
        const query = (input.value || "").trim().toLocaleLowerCase();
        shell.querySelectorAll(SELECTORS.thread).forEach((row) => {
            const text = (row.dataset.search || row.textContent || "").toLocaleLowerCase();
            row.hidden = Boolean(query && !text.includes(query));
        });
    }

    function setModal(open) {
        const modal = document.querySelector(SELECTORS.modal);
        if (!modal) return;
        modal.classList.toggle("show", open);
        modal.setAttribute("aria-hidden", open ? "false" : "true");
        if (open) {
            const first = modal.querySelector('input[name="participant_ids"]');
            window.setTimeout(() => first?.focus(), 50);
        }
    }

    function openThread(link) {
        const shell = link.closest(SELECTORS.shell);
        const frame = shell?.querySelector(SELECTORS.frame);
        if (!shell || !frame) return;
        const href = link.getAttribute("href");
        if (!href) return;

        shell.querySelectorAll(SELECTORS.thread).forEach((row) => row.classList.remove("active"));
        link.classList.add("active");
        shell.classList.add("ep-chat-open");
        shell.querySelector(SELECTORS.empty)?.classList.add("d-none");
        frame.classList.add("show");
        if (frame.getAttribute("src") !== href) frame.setAttribute("src", href);
    }

    function closeThread(shell) {
        const frame = shell?.querySelector(SELECTORS.frame);
        if (!shell) return;
        shell.classList.remove("ep-chat-open");
        shell.querySelectorAll(SELECTORS.thread).forEach((row) => row.classList.remove("active"));
        frame?.classList.remove("show");
        if (frame) frame.setAttribute("src", "about:blank");
    }

    function bind() {
        const shell = document.querySelector(SELECTORS.shell);
        if (!shell || shell.dataset.epChatsHomeBound === "1") return;
        shell.dataset.epChatsHomeBound = "1";

        shell.querySelector(SELECTORS.search)?.addEventListener("input", (event) => filterChats(event.currentTarget));
        shell.querySelector(SELECTORS.newChat)?.addEventListener("click", (event) => {
            event.preventDefault();
            setModal(true);
        });
        document.querySelectorAll(SELECTORS.closeNewChat).forEach((button) => {
            button.addEventListener("click", (event) => {
                event.preventDefault();
                setModal(false);
            });
        });
        shell.querySelectorAll(SELECTORS.thread).forEach((link) => {
            link.addEventListener("click", (event) => {
                event.preventDefault();
                openThread(link);
            });
        });

        const frame = shell.querySelector(SELECTORS.frame);
        frame?.addEventListener("load", () => {
            if (frame.getAttribute("src") && frame.getAttribute("src") !== "about:blank") {
                shell.classList.add("ep-chat-open");
                frame.classList.add("show");
            }
        });

        window.addEventListener("message", (event) => {
            if (event.origin !== window.location.origin) return;
            if (event.data?.type === "employee-discuss-back-to-chats") closeThread(shell);
        });
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind, { once: true });
    else bind();
    window.addEventListener("pageshow", bind);
})();
