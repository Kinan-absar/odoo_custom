(function () {
    "use strict";

    const root = document.getElementById("absar_chat_root");
    if (!root) return;

    const state = {
        session: null,
        channels: [],
        activeChannel: null,
        messages: [],
        search: "",
        loadingChannels: true,
        loadingMessages: false,
        sending: false,
        pollTimer: null,
    };

    let rpcCounter = 1;

    async function rpc(route, params = {}) {
        const response = await fetch(route, {
            method: "POST",
            credentials: "same-origin",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params,
                id: rpcCounter++,
            }),
        });
        if (!response.ok) {
            throw new Error(`${route} returned HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (payload.error) {
            const message = payload.error.data?.message || payload.error.message || "Odoo request failed";
            throw new Error(message);
        }
        return payload.result;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function safeImage(url, fallback = "/web/static/img/avatar.png") {
        if (!url || typeof url !== "string" || !(url.startsWith("/") || url.startsWith("data:image/"))) return fallback;
        return url;
    }

    function formatTime(value) {
        if (!value) return "";
        const date = new Date(value.replace(" ", "T") + (value.includes("Z") ? "" : "Z"));
        if (Number.isNaN(date.getTime())) return "";
        return date.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
    }

    function renderShell() {
        root.innerHTML = `
            <div class="absar-app-container ${state.activeChannel ? "chat-open" : ""}">
                <aside class="absar-sidebar">
                    <div class="absar-sidebar-header">
                        <div class="absar-brand">
                            <div class="absar-logo-badge">A</div>
                            <div class="absar-brand-info">
                                <span class="absar-brand-title">Absar Chat</span>
                                <span class="absar-brand-subtitle">Internal Messaging</span>
                            </div>
                        </div>
                    </div>
                    <div class="absar-sidebar-search">
                        <div class="absar-search-input-wrapper">
                            <span class="absar-search-icon">&#128269;</span>
                            <input id="absar_search" class="absar-search-input" type="search" placeholder="Search conversations..." value="${escapeHtml(state.search)}" />
                        </div>
                    </div>
                    <div id="absar_conversation_list" class="absar-conversation-list"></div>
                    <div class="absar-sidebar-footer">
                        <div class="absar-user-profile">
                            <img class="absar-user-avatar" src="${safeImage(state.session?.avatar_url)}" alt="Employee"/>
                            <div class="absar-user-meta">
                                <span class="absar-user-name">${escapeHtml(state.session?.employee_name || "Employee")}</span>
                                <span class="absar-user-role">${escapeHtml(state.session?.job_title || state.session?.department || "Staff")}</span>
                            </div>
                        </div>
                    </div>
                </aside>
                <main id="absar_main" class="absar-main"></main>
            </div>`;

        const search = document.getElementById("absar_search");
        search?.addEventListener("input", (ev) => {
            state.search = ev.target.value || "";
            renderConversationList();
        });
        renderConversationList();
        renderMain();
    }

    function renderConversationList() {
        const list = document.getElementById("absar_conversation_list");
        if (!list) return;
        if (state.loadingChannels) {
            list.innerHTML = '<div class="absar-list-status">Loading conversations...</div>';
            return;
        }
        const query = state.search.trim().toLowerCase();
        const channels = query ? state.channels.filter((c) => (c.name || "").toLowerCase().includes(query)) : state.channels;
        if (!channels.length) {
            list.innerHTML = '<div class="absar-list-status">No conversations found</div>';
            return;
        }
        list.innerHTML = channels.map((channel) => {
            const last = channel.last_message || {};
            return `
                <button class="absar-chat-item ${state.activeChannel?.id === channel.id ? "active" : ""}" data-channel-id="${channel.id}" type="button">
                    <div class="absar-chat-avatar-wrapper">
                        <img class="absar-chat-avatar" src="${safeImage(channel.avatar_url)}" alt="${escapeHtml(channel.name)}" loading="lazy"/>
                    </div>
                    <div class="absar-chat-info">
                        <div class="absar-chat-info-top">
                            <span class="absar-chat-name">${escapeHtml(channel.name || "Conversation")}</span>
                            <span class="absar-chat-time">${escapeHtml(formatTime(last.date))}</span>
                        </div>
                        <div class="absar-chat-info-bottom">
                            <span class="absar-chat-preview">${escapeHtml(last.body || "No messages yet")}</span>
                            ${channel.unread_count > 0 ? `<span class="absar-unread-badge">${Math.min(99, channel.unread_count)}${channel.unread_count > 99 ? "+" : ""}</span>` : ""}
                        </div>
                    </div>
                </button>`;
        }).join("");
        list.querySelectorAll("[data-channel-id]").forEach((el) => {
            el.addEventListener("click", () => {
                const id = Number(el.dataset.channelId);
                const channel = state.channels.find((c) => c.id === id);
                if (channel) selectChannel(channel);
            });
        });
    }

    function renderMain() {
        const main = document.getElementById("absar_main");
        if (!main) return;
        if (!state.activeChannel) {
            main.innerHTML = `
                <div class="absar-empty-state">
                    <div class="absar-empty-icon">&#128172;</div>
                    <h2 class="absar-empty-title">Absar Chat</h2>
                    <p class="absar-empty-desc">Select a conversation to read and send messages.</p>
                </div>`;
            return;
        }
        main.innerHTML = `
            <header class="absar-chat-header">
                <div class="absar-header-left">
                    <button id="absar_back" class="absar-back-btn" type="button" aria-label="Back">&#8592;</button>
                    <img class="absar-header-avatar" src="${safeImage(state.activeChannel.avatar_url)}" alt="${escapeHtml(state.activeChannel.name)}"/>
                    <div class="absar-header-details">
                        <span class="absar-header-name">${escapeHtml(state.activeChannel.name || "Conversation")}</span>
                    </div>
                </div>
            </header>
            <div id="absar_timeline" class="absar-timeline"></div>
            <div class="absar-composer-bar">
                <textarea id="absar_composer" class="absar-composer-input" rows="1" placeholder="Type a message... (Enter to send, Shift+Enter for new line)"></textarea>
                <button id="absar_send" class="absar-send-btn" type="button" title="Send message">&#10148;</button>
            </div>`;
        document.getElementById("absar_back")?.addEventListener("click", () => {
            state.activeChannel = null;
            state.messages = [];
            renderShell();
        });
        const composer = document.getElementById("absar_composer");
        composer?.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter" && !ev.shiftKey) {
                ev.preventDefault();
                sendMessage();
            }
        });
        document.getElementById("absar_send")?.addEventListener("click", sendMessage);
        renderMessages();
    }

    function renderMessages() {
        const timeline = document.getElementById("absar_timeline");
        if (!timeline) return;
        if (state.loadingMessages) {
            timeline.innerHTML = '<div class="absar-list-status">Loading messages...</div>';
            return;
        }
        if (!state.messages.length) {
            timeline.innerHTML = '<div class="absar-list-status">No messages yet. Start by saying hello.</div>';
            return;
        }
        timeline.innerHTML = state.messages.map((msg) => `
            <div class="absar-message-row ${msg.is_current_user ? "outgoing" : "incoming"}">
                ${msg.is_current_user ? "" : `<img class="absar-msg-avatar" src="${safeImage(msg.author_avatar)}" alt="${escapeHtml(msg.author_name)}"/>`}
                <div class="absar-message-bubble">
                    ${(!msg.is_current_user && !state.activeChannel.is_direct) ? `<div class="absar-msg-author">${escapeHtml(msg.author_name || "")}</div>` : ""}
                    <div class="absar-msg-body">${msg.body || ""}</div>
                    <span class="absar-msg-time">${escapeHtml(formatTime(msg.date))}</span>
                </div>
            </div>`).join("");
        requestAnimationFrame(() => { timeline.scrollTop = timeline.scrollHeight; });
    }

    async function loadChannels() {
        state.loadingChannels = true;
        renderConversationList();
        const channels = await rpc("/chat/api/channels");
        state.channels = Array.isArray(channels) ? channels : [];
        state.loadingChannels = false;
        renderConversationList();
    }

    async function selectChannel(channel) {
        state.activeChannel = channel;
        channel.unread_count = 0;
        state.messages = [];
        state.loadingMessages = true;
        renderShell();
        try {
            const data = await rpc("/chat/api/messages", {channel_id: channel.id, limit: 50});
            state.messages = data?.messages || [];
            await rpc("/chat/api/mark_as_read", {channel_id: channel.id}).catch(() => null);
        } finally {
            state.loadingMessages = false;
            renderMessages();
            renderConversationList();
        }
    }

    async function sendMessage() {
        if (state.sending || !state.activeChannel) return;
        const composer = document.getElementById("absar_composer");
        const text = (composer?.value || "").trim();
        if (!text) return;
        state.sending = true;
        const button = document.getElementById("absar_send");
        if (button) button.disabled = true;
        try {
            const result = await rpc("/chat/api/message/send", {channel_id: state.activeChannel.id, body: text});
            if (result?.success && result.message) {
                state.messages.push(result.message);
                if (composer) composer.value = "";
                renderMessages();
                await loadChannels();
            }
        } catch (err) {
            showToast(err.message || "Message could not be sent", true);
        } finally {
            state.sending = false;
            if (button) button.disabled = false;
            composer?.focus();
        }
    }

    async function syncActiveChannel() {
        if (!state.activeChannel || document.visibilityState !== "visible") return;
        try {
            const data = await rpc("/chat/api/messages", {channel_id: state.activeChannel.id, limit: 50});
            const next = data?.messages || [];
            const oldLast = state.messages.at(-1)?.id || 0;
            const newLast = next.at(-1)?.id || 0;
            if (oldLast !== newLast || next.length !== state.messages.length) {
                state.messages = next;
                renderMessages();
                await rpc("/chat/api/mark_as_read", {channel_id: state.activeChannel.id}).catch(() => null);
                loadChannels().catch(() => null);
            }
        } catch (_) {
            // Temporary fallback sync must not disrupt the UI.
        }
    }

    function showToast(message, isError = false) {
        let toast = document.getElementById("absar_toast");
        if (!toast) {
            toast = document.createElement("div");
            toast.id = "absar_toast";
            toast.className = "absar-toast";
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.classList.toggle("error", isError);
        toast.classList.add("show");
        window.clearTimeout(showToast.timer);
        showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3500);
    }

    function showFatal(err) {
        console.error("[Absar Chat] startup failed", err);
        root.innerHTML = `
            <div class="absar-chat-splash">
                <div class="absar-fatal-card">
                    <strong>Absar Chat could not start.</strong>
                    <span>${escapeHtml(err?.message || "Unknown startup error")}</span>
                    <button id="absar_retry" type="button">Retry</button>
                </div>
            </div>`;
        document.getElementById("absar_retry")?.addEventListener("click", () => window.location.reload());
    }

    async function bootstrap() {
        try {
            console.log("[Absar Chat] bootstrap started");
            state.session = await rpc("/chat/api/session");
            console.log("[Absar Chat] session ready");
            renderShell();
            await loadChannels();
            console.log("[Absar Chat] conversations loaded");

            state.pollTimer = window.setInterval(() => {
                if (document.visibilityState === "visible" && state.activeChannel) {
                    syncActiveChannel();
                }
            }, 5000);

            document.addEventListener("visibilitychange", () => {
                if (document.visibilityState === "visible") {
                    if (state.activeChannel) syncActiveChannel();
                    loadChannels().catch(() => null);
                }
            });
        } catch (err) {
            showFatal(err);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootstrap, {once: true});
    } else {
        bootstrap();
    }
})();
