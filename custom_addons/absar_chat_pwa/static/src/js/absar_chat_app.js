/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount, useRef, mount } from "@odoo/owl";
import { makeEnv, startServices } from "@web/env";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

export class AbsarChatApp extends Component {
    static template = "absar_chat_pwa.AbsarChatApp";

    setup() {
        this.timelineRef = useRef("timeline");
        this.composerRef = useRef("composer");

        // Obtain native Odoo 18 bus_service
        try {
            this.busService = useService("bus_service");
        } catch {
            this.busService = this.env.services?.bus_service || null;
        }

        this.state = useState({
            session: window.ABSAR_CHAT_SESSION || {},
            channels: [],
            activeChannelId: null,
            activeChannel: null,
            messages: [],
            searchQuery: "",
            composerText: "",
            isLoadingChannels: true,
            isLoadingMessages: false,
            isSending: false,
            isMobile: window.innerWidth < 768,
        });

        this.pollTimer = null;
        this.resizeHandler = this.onWindowResize.bind(this);
        this.visibilityHandler = this.onVisibilityChange.bind(this);
        this.busNotificationHandler = this.onBusNotification.bind(this);

        onMounted(() => {
            window.addEventListener("resize", this.resizeHandler);
            document.addEventListener("visibilitychange", this.visibilityHandler);

            this.loadChannels();

            // Native Odoo 18 Bus integration (primary real-time channel)
            if (this.busService) {
                // In Odoo 18, bus_service inherits from EventTarget and dispatches 'notification'
                if (typeof this.busService.addEventListener === "function") {
                    this.busService.addEventListener("notification", this.busNotificationHandler);
                }
                // Also subscribe to specific discuss notification types if supported
                if (typeof this.busService.subscribe === "function") {
                    try {
                        this.busService.subscribe("discuss.channel", (payload) => {
                            this.handleSingleNotification("discuss.channel", payload);
                        });
                        this.busService.subscribe("mail.record/insert", (payload) => {
                            this.handleSingleNotification("mail.record/insert", payload);
                        });
                    } catch (e) {
                        console.debug("Absar Chat: Bus subscribe fallback handled", e);
                    }
                }
            }

            // TEMPORARY RELIABILITY FALLBACK (5-second interval):
            // Strictly paused when document is hidden/backgrounded or when no chat is open
            this.pollTimer = setInterval(() => {
                if (document.visibilityState !== "visible" || !this.state.activeChannelId) {
                    return;
                }
                this.syncActiveChannelMessages();
            }, 5000);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this.resizeHandler);
            document.removeEventListener("visibilitychange", this.visibilityHandler);

            if (this.pollTimer) {
                clearInterval(this.pollTimer);
                this.pollTimer = null;
            }

            if (this.busService && typeof this.busService.removeEventListener === "function") {
                this.busService.removeEventListener("notification", this.busNotificationHandler);
            }
        });
    }

    onWindowResize() {
        this.state.isMobile = window.innerWidth < 768;
    }

    onVisibilityChange() {
        // Immediately synchronize active chat when the user brings the PWA back into view
        if (document.visibilityState === "visible" && this.state.activeChannelId) {
            this.syncActiveChannelMessages();
        }
    }

    get filteredChannels() {
        const query = this.state.searchQuery.trim().toLowerCase();
        if (!query) {
            return this.state.channels;
        }
        return this.state.channels.filter((c) =>
            (c.name || "").toLowerCase().includes(query)
        );
    }

    async loadChannels() {
        try {
            this.state.isLoadingChannels = true;
            const data = await rpc("/chat/api/channels");
            this.state.channels = data || [];

            // Register bus channels for each conversation if supported
            if (this.busService && typeof this.busService.addChannel === "function") {
                for (const ch of this.state.channels) {
                    try {
                        this.busService.addChannel(`discuss.channel_${ch.id}`);
                    } catch {
                        // ignore unsupported channel format
                    }
                }
            }
        } catch (err) {
            console.error("Failed to load Absar Chat conversations:", err);
        } finally {
            this.state.isLoadingChannels = false;
        }
    }

    async selectChannel(channel) {
        if (!channel || this.state.activeChannelId === channel.id) {
            return;
        }
        this.state.activeChannelId = channel.id;
        this.state.activeChannel = channel;
        this.state.messages = [];
        this.state.isLoadingMessages = true;

        try {
            const data = await rpc("/chat/api/messages", {
                channel_id: channel.id,
                limit: 50,
            });
            this.state.messages = data.messages || [];
            
            // Mark conversation as read in Odoo via native Discuss marker
            rpc("/chat/api/mark_as_read", { channel_id: channel.id }).catch(() => {});
            channel.unread_count = 0;

            this.scrollToBottom();
        } catch (err) {
            console.error("Failed to load messages:", err);
        } finally {
            this.state.isLoadingMessages = false;
        }
    }

    closeActiveChat() {
        this.state.activeChannelId = null;
        this.state.activeChannel = null;
    }

    scrollToBottom() {
        setTimeout(() => {
            if (this.timelineRef.el) {
                this.timelineRef.el.scrollTop = this.timelineRef.el.scrollHeight;
            }
        }, 50);
    }

    onComposerKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    async sendMessage() {
        const text = this.state.composerText.trim();
        if (!text || !this.state.activeChannelId || this.state.isSending) {
            return;
        }

        const channelId = this.state.activeChannelId;
        this.state.isSending = true;

        try {
            const res = await rpc("/chat/api/message/send", {
                channel_id: channelId,
                body: text,
            });

            if (res && res.success && res.message) {
                this.state.messages.push(res.message);
                this.state.composerText = "";

                // Update channel last message in sidebar
                if (this.state.activeChannel) {
                    this.state.activeChannel.last_message = {
                        body: text.length > 55 ? text.substring(0, 52) + "..." : text,
                        date: res.message.date,
                        author_name: res.message.author_name,
                    };
                }

                this.scrollToBottom();
            }
        } catch (err) {
            console.error("Error sending message to Odoo Discuss:", err);
        } finally {
            this.state.isSending = false;
            if (this.composerRef.el) {
                this.composerRef.el.focus();
            }
        }
    }

    async syncActiveChannelMessages() {
        if (!this.state.activeChannelId || document.visibilityState !== "visible") {
            return;
        }
        try {
            const data = await rpc("/chat/api/messages", {
                channel_id: this.state.activeChannelId,
                limit: 50,
            });
            if (data && data.messages) {
                const currentIds = new Set(this.state.messages.map((m) => m.id));
                const newMessages = data.messages.filter((m) => !currentIds.has(m.id));
                if (newMessages.length > 0) {
                    this.state.messages = data.messages;
                    this.scrollToBottom();
                    rpc("/chat/api/mark_as_read", { channel_id: this.state.activeChannelId }).catch(() => {});
                }
            }
        } catch {
            // Background sync silent failure
        }
    }

    onBusNotification({ detail: notifications }) {
        if (!Array.isArray(notifications)) {
            return;
        }
        for (const notif of notifications) {
            this.handleSingleNotification(notif.type, notif.payload);
        }
    }

    handleSingleNotification(type, payload) {
        if (!type || !payload) return;

        // Check if notification affects discuss channels
        const isDiscussNotif =
            type.startsWith("discuss.channel") ||
            type.startsWith("mail.record") ||
            type.startsWith("mail.message");

        if (!isDiscussNotif) return;

        // Check if active channel is affected
        const notifChannelId =
            payload.channel_id ||
            payload.Thread?.id ||
            (Array.isArray(payload.Thread) ? payload.Thread[0]?.id : null);

        if (this.state.activeChannelId && notifChannelId === this.state.activeChannelId) {
            this.syncActiveChannelMessages();
        } else {
            // Refresh conversation list for new last_message or unread count
            this.loadChannels();
        }
    }

    formatTime(dateStr) {
        if (!dateStr) return "";
        try {
            const d = new Date(dateStr);
            return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        } catch {
            return dateStr;
        }
    }

    formatDate(dateStr) {
        if (!dateStr) return "";
        try {
            const d = new Date(dateStr);
            const today = new Date();
            if (d.toDateString() === today.toDateString()) {
                return "Today";
            }
            return d.toLocaleDateString([], { month: "short", day: "numeric" });
        } catch {
            return dateStr;
        }
    }
}

// Bootstrap Absar Chat using native Odoo 18 service environment
document.addEventListener("DOMContentLoaded", async () => {
    const rootEl = document.getElementById("absar_chat_root");
    if (!rootEl) return;

    try {
        const env = makeEnv();
        await startServices(env);
        await mount(AbsarChatApp, rootEl, { env });
    } catch (err) {
        console.error("Absar Chat mount with Odoo services:", err);
        try {
            await mount(AbsarChatApp, rootEl);
        } catch (mountErr) {
            console.error("Absar Chat standalone mount fallback failed:", mountErr);
        }
    }
});

