(function () {
    "use strict";

    const $ = (sel, root = document) => root.querySelector(sel);
    const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
    const esc = (value) => String(value == null ? "" : value)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#039;");

    async function rpc(route, params = {}) {
        const response = await fetch(route, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params, id: Date.now() + Math.floor(Math.random() * 999) }),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const json = await response.json();
        if (json.error) throw new Error(json.error?.data?.message || json.error?.message || "RPC error");
        return json.result;
    }

    class AbsarChat {
        constructor() {
            this.userId = Number(document.body.dataset.currentUserId || 0);
            this.userName = document.body.dataset.currentUserName || "Employee";
            this.userAvatar = document.body.dataset.currentAvatar || "";
            this.view = "chats";
            this.threads = [];
            this.contacts = [];
            this.presence = {};
            this.currentThreadId = null;
            this.currentThread = null;
            this.currentMessages = [];
            this.replyTo = null;
            this.pendingFiles = [];
            this.lastMessageIds = new Map();
            this.selectedPeople = new Set();
            this.modalMode = "new";
            this.modalPeople = null;
            this.deferredInstall = null;
            this.recorder = null;
            this.recordingChunks = [];
            this.recordingStartedAt = null;
            this.messageTimer = null;
            this.threadTimer = null;
            this.presenceTimer = null;
            this.typingTimer = null;
            this.lastTyping = false;
            this.previousUnreadTotal = 0;
            this.bound = false;
            this.emojis = ["😀","😁","😂","😊","😍","👍","❤️","🎉","😮","😢","🙏","👏","💯","✅","🔥","👋","🤝","👌","📌","📎","💬","🚀","⭐","☕"];
            this.init();
        }

        async init() {
            this.bind();
            this.buildEmojiPanel();
            this.bindInstallPrompt();
            try {
                await Promise.all([this.refreshContacts(), this.refreshThreads(false), this.refreshPresence()]);
                this.restoreThreadFromUrl();
                this.startTimers();
            } catch (error) {
                console.error("[Absar Chat] startup failed", error);
                $("#ac-thread-list").innerHTML = `<div class="ac-error">Could not load Absar Chat.<br/>${esc(error.message)}</div>`;
            }
        }

        bind() {
            if (this.bound) return;
            this.bound = true;
            $$(".ac-rail-btn").forEach(btn => btn.addEventListener("click", () => this.setView(btn.dataset.view)));
            $("#ac-new-chat").addEventListener("click", () => this.openNewChat());
            $("#ac-empty-new").addEventListener("click", () => this.openNewChat());
            $("#ac-new-close").addEventListener("click", () => this.closeNewChat());
            $("#ac-modal-backdrop").addEventListener("click", () => this.closeNewChat());
            $("#ac-new-start").addEventListener("click", () => this.startConversation());
            $("#ac-new-search").addEventListener("input", () => this.renderNewPeople());
            $("#ac-thread-search").addEventListener("input", () => this.renderThreads());
            $("#ac-people-search").addEventListener("input", () => this.renderPeople());
            $("#ac-composer").addEventListener("submit", (ev) => { ev.preventDefault(); this.sendMessage(); });
            $("#ac-message-input").addEventListener("keydown", (ev) => {
                if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); this.sendMessage(); }
            });
            $("#ac-message-input").addEventListener("input", () => { this.autogrowComposer(); this.handleTyping(true); });
            $("#ac-message-input").addEventListener("blur", () => this.handleTyping(false));
            $("#ac-attach").addEventListener("click", () => $("#ac-file-input").click());
            $("#ac-file-input").addEventListener("change", (ev) => this.queueFiles(ev.target.files));
            $("#ac-voice").addEventListener("click", () => this.toggleVoiceRecording());
            $("#ac-emoji").addEventListener("click", () => $("#ac-emoji-panel").classList.toggle("is-hidden"));
            $("#ac-reply-cancel").addEventListener("click", () => this.setReply(null));
            $("#ac-audio-call").addEventListener("click", () => this.callCurrent("audio"));
            $("#ac-video-call").addEventListener("click", () => this.callCurrent("video"));
            $("#ac-chat-info").addEventListener("click", () => this.toggleInfo(true));
            $("#ac-info-close").addEventListener("click", () => this.toggleInfo(false));
            $("#ac-search-messages").addEventListener("click", () => { $("#ac-message-search-bar").classList.remove("is-hidden"); $("#ac-message-search-input").focus(); });
            $("#ac-message-search-close").addEventListener("click", () => { $("#ac-message-search-bar").classList.add("is-hidden"); $("#ac-message-search-input").value = ""; this.renderMessages(); });
            $("#ac-message-search-input").addEventListener("input", () => this.renderMessages());
            $("#ac-mobile-back").addEventListener("click", () => this.closeMobileConversation());
            $("#ac-install").addEventListener("click", () => this.installApp());
            $("#ac-notifications").addEventListener("click", () => this.enableNotifications());
            document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") this.syncNow(); });
            window.addEventListener("popstate", () => this.restoreThreadFromUrl());
        }

        bindInstallPrompt() {
            window.addEventListener("beforeinstallprompt", (ev) => {
                ev.preventDefault();
                this.deferredInstall = ev;
                $("#ac-install").textContent = "Install app";
            });
        }

        buildEmojiPanel() {
            const panel = $("#ac-emoji-panel");
            panel.innerHTML = this.emojis.map(e => `<button type="button">${e}</button>`).join("");
            panel.addEventListener("click", ev => {
                const btn = ev.target.closest("button"); if (!btn) return;
                const input = $("#ac-message-input");
                input.value += btn.textContent; input.focus(); this.autogrowComposer();
            });
        }

        setView(view) {
            this.view = view;
            $$(".ac-rail-btn").forEach(btn => btn.classList.toggle("is-active", btn.dataset.view === view));
            const sidebar = $("#ac-sidebar"), main = $("#ac-main");
            $("#ac-conversation").classList.add("is-hidden");
            $("#ac-empty").classList.add("is-hidden");
            $$(".ac-page-view").forEach(el => el.classList.add("is-hidden"));
            main.classList.remove("mobile-open", "mobile-page");
            if (view === "chats") {
                sidebar.classList.remove("is-hidden");
                if (this.currentThreadId) { $("#ac-conversation").classList.remove("is-hidden"); if (innerWidth <= 700) main.classList.add("mobile-open"); }
                else $("#ac-empty").classList.remove("is-hidden");
            } else {
                sidebar.classList.toggle("is-hidden", innerWidth <= 700);
                main.classList.add("mobile-page");
                const target = $(`#ac-${view}-view`); if (target) target.classList.remove("is-hidden");
                if (view === "calls") this.refreshCallHistory();
                if (view === "people") this.renderPeople();
            }
        }

        async refreshContacts() {
            const rows = await rpc("/employee_portal/call/contacts", {});
            this.contacts = Array.isArray(rows) ? rows : [];
            this.renderPeople();
            this.renderNewPeople();
        }

        async refreshPresence() {
            try {
                const result = await rpc("/employee_portal/call/presence", { active: true });
                this.presence = result?.statuses || {};
                this.contacts.forEach(c => c.presence = this.presence[String(c.user_id)] || c.presence || "offline");
                this.renderPeople(); this.renderNewPeople(); this.updateConversationPresence();
            } catch (_) {}
        }

        async refreshThreads(notify = true) {
            const result = await rpc("/employee_portal/chat/threads", {});
            const newThreads = result?.threads || [];
            const unreadTotal = Number(result?.unread_total || 0);
            if (notify && unreadTotal > this.previousUnreadTotal && document.visibilityState !== "visible") {
                this.notify("Absar Chat", "You have a new message.");
            }
            this.previousUnreadTotal = unreadTotal;
            this.threads = newThreads;
            $("#ac-chat-badge").textContent = unreadTotal > 99 ? "99+" : unreadTotal;
            $("#ac-chat-badge").classList.toggle("is-hidden", unreadTotal <= 0);
            this.renderThreads();
            if (this.currentThreadId) {
                this.currentThread = this.threads.find(t => Number(t.id) === Number(this.currentThreadId)) || this.currentThread;
            }
        }

        renderThreads() {
            const list = $("#ac-thread-list");
            const q = ($("#ac-thread-search").value || "").trim().toLowerCase();
            const rows = this.threads.filter(t => !q || (t.name || "").toLowerCase().includes(q) || (t.preview || "").toLowerCase().includes(q));
            if (!rows.length) { list.innerHTML = `<div class="ac-loading">${q ? "No matching conversations." : "No conversations yet."}</div>`; return; }
            list.innerHTML = rows.map(t => {
                const active = Number(t.id) === Number(this.currentThreadId) ? " is-active" : "";
                return `<article class="ac-thread${active}" data-thread-id="${t.id}">
                    <img class="ac-thread-avatar" src="${esc(t.avatar_url)}" alt="" onerror="this.src='/absar_chat_pwa/static/icons/icon-192.png'"/>
                    <div class="ac-thread-copy"><div class="ac-thread-name">${esc(t.name || "Conversation")}${t.is_group ? ' <i class="fa fa-users" style="font-size:10px;color:#8893a0"></i>' : ""}</div><div class="ac-thread-preview">${esc(t.preview || "No messages yet")}</div></div>
                    <div class="ac-thread-meta"><span class="ac-thread-time">${this.formatListTime(t.last_message_date)}</span>${t.unread ? `<b class="ac-unread">${t.unread > 99 ? "99+" : t.unread}</b>` : ""}</div>
                </article>`;
            }).join("");
            $$(".ac-thread", list).forEach(row => row.addEventListener("click", () => this.openThread(Number(row.dataset.threadId))));
        }

        restoreThreadFromUrl() {
            const id = Number(new URL(location.href).searchParams.get("thread") || 0);
            if (id && id !== this.currentThreadId) this.openThread(id, false);
        }

        async openThread(threadId, push = true) {
            this.currentThreadId = Number(threadId);
            this.currentThread = this.threads.find(t => Number(t.id) === this.currentThreadId) || null;
            if (push) history.pushState({}, "", `/chat/?thread=${this.currentThreadId}`);
            this.setView("chats");
            $("#ac-empty").classList.add("is-hidden");
            $("#ac-conversation").classList.remove("is-hidden");
            if (innerWidth <= 700) $("#ac-main").classList.add("mobile-open");
            this.renderThreads();
            await this.refreshMessages(true);
        }

        closeMobileConversation() {
            $("#ac-main").classList.remove("mobile-open");
            history.pushState({}, "", "/chat/");
        }

        async refreshMessages(scrollBottom = false) {
            if (!this.currentThreadId || document.visibilityState !== "visible") return;
            try {
                const result = await rpc("/employee_portal/chat/messages", { thread_id: this.currentThreadId, limit: 150 });
                if (result?.error) return;
                this.currentThread = Object.assign({}, this.currentThread || {}, result.thread || {});
                const oldLast = this.currentMessages.length ? this.currentMessages[this.currentMessages.length - 1].id : 0;
                this.currentMessages = result?.messages || [];
                this.renderConversationHeader();
                this.renderMessages();
                this.renderTyping(result?.typing || []);
                this.renderInfo();
                const newLast = this.currentMessages.length ? this.currentMessages[this.currentMessages.length - 1].id : 0;
                if (scrollBottom || (newLast && newLast !== oldLast)) this.scrollMessagesToBottom();
                await rpc("/employee_portal/chat/mark_read", { thread_id: this.currentThreadId }).catch(() => {});
                this.refreshThreads(false).catch(() => {});
            } catch (error) { console.warn("[Absar Chat] message refresh failed", error); }
        }

        renderConversationHeader() {
            const t = this.currentThread || {};
            $("#ac-chat-title").textContent = t.name || "Conversation";
            const avatar = this.currentThread?.avatar_url || this.threads.find(x => Number(x.id) === Number(this.currentThreadId))?.avatar_url || "/absar_chat_pwa/static/icons/icon-192.png";
            $("#ac-chat-avatar").src = avatar;
            const others = (t.participants || []).filter(p => !p.is_me);
            let subtitle = t.is_group ? `${t.participant_count || others.length + 1} participants` : (others[0] ? this.presenceLabel(this.presence[String(others[0].user_id)] || "offline") : "Employee");
            $("#ac-chat-subtitle").textContent = subtitle;
        }

        updateConversationPresence() { if (this.currentThread) this.renderConversationHeader(); }

        renderMessages() {
            const box = $("#ac-messages");
            const query = ($("#ac-message-search-input").value || "").trim().toLowerCase();
            let rows = this.currentMessages;
            if (query) rows = rows.filter(m => (m.body || "").toLowerCase().includes(query) || (m.author || "").toLowerCase().includes(query) || (m.attachments || []).some(a => (a.name || "").toLowerCase().includes(query)));
            if (!rows.length) { box.innerHTML = `<div class="ac-loading">${query ? "No matching messages." : "No messages yet. Say hello."}</div>`; return; }
            let lastDate = "";
            box.innerHTML = rows.map(m => {
                const dateKey = this.dateKey(m.date);
                const sep = dateKey !== lastDate ? `<div class="ac-day-sep"><span>${esc(this.formatDay(m.date))}</span></div>` : "";
                lastDate = dateKey;
                const avatar = m.avatar_url ? `<img class="ac-msg-avatar" src="${esc(m.avatar_url)}" alt=""/>` : "";
                const reply = m.reply_to ? `<div class="ac-reply-quote"><strong>${esc(m.reply_to.author)}</strong>${esc(m.reply_to.body)}</div>` : "";
                const attachments = this.renderAttachments(m.attachments || []);
                const reactions = (m.reactions || []).length ? `<div class="ac-reaction-row">${m.reactions.map(r => `<button class="ac-reaction-chip${r.mine ? " mine" : ""}" data-react="${esc(r.content)}" data-message-id="${m.id}" title="${esc((r.names || []).join(', '))}">${esc(r.content)} ${r.count}</button>`).join("")}</div>` : "";
                const read = m.mine && (m.read_by || []).length ? `<span class="ac-read" title="Read by ${esc((m.read_by || []).join(', '))}">✓✓</span>` : (m.mine ? "✓" : "");
                return `${sep}<div class="ac-msg-row${m.mine ? " mine" : ""}" data-message-id="${m.id}">${m.mine ? "" : avatar}<div class="ac-msg-bubble">
                    <div class="ac-msg-actions"><button data-action="reply" title="Reply"><i class="fa fa-reply"></i></button><button data-action="react" title="React">☺</button></div>
                    ${!m.mine && this.currentThread?.is_group ? `<div class="ac-msg-author">${esc(m.author)}</div>` : ""}${reply}${m.body ? `<div class="ac-msg-text">${esc(m.body)}</div>` : ""}${attachments}${reactions}<div class="ac-msg-foot"><span>${esc(this.formatTime(m.date))}</span><span>${read}</span></div>
                </div></div>`;
            }).join("");
            $$("[data-action='reply']", box).forEach(btn => btn.addEventListener("click", ev => { const msg = this.messageByNode(ev.currentTarget); if (msg) this.setReply(msg); }));
            $$("[data-action='react']", box).forEach(btn => btn.addEventListener("click", ev => { const msg = this.messageByNode(ev.currentTarget); if (msg) this.quickReact(msg.id); }));
            $$(".ac-reaction-chip", box).forEach(btn => btn.addEventListener("click", () => this.toggleReaction(Number(btn.dataset.messageId), btn.dataset.react)));
        }

        messageByNode(node) { const id = Number(node.closest(".ac-msg-row")?.dataset.messageId || 0); return this.currentMessages.find(m => Number(m.id) === id); }

        renderAttachments(items) {
            if (!items.length) return "";
            return `<div class="ac-attachments">${items.map(a => {
                const previewUrl = `/chat/attachment/${a.id}`;
                const mt = a.mimetype || "";
                if (mt.startsWith("image/")) return `<a href="${previewUrl}" target="_blank"><img class="ac-image-preview" src="${previewUrl}" alt="${esc(a.name)}"/></a>`;
                if (mt.startsWith("audio/")) return `<audio class="ac-audio-preview" controls preload="metadata" src="${previewUrl}"></audio>`;
                return `<a class="ac-attachment" href="${esc(a.url)}" target="_blank"><i class="fa ${mt.includes('pdf') ? 'fa-file-pdf-o' : 'fa-file-o'}"></i><span class="ac-attachment-copy"><strong>${esc(a.name)}</strong><span>${this.formatBytes(a.size)}</span></span><i class="fa fa-download"></i></a>`;
            }).join("")}</div>`;
        }

        renderTyping(names) {
            const el = $("#ac-typing");
            if (!names.length) { el.classList.add("is-hidden"); return; }
            el.textContent = `${names.join(", ")} ${names.length > 1 ? "are" : "is"} typing…`;
            el.classList.remove("is-hidden");
        }

        setReply(message) {
            this.replyTo = message;
            const bar = $("#ac-reply-bar");
            if (!message) { bar.classList.add("is-hidden"); return; }
            $("#ac-reply-author").textContent = message.author || "Employee";
            $("#ac-reply-text").textContent = message.body || "Attachment";
            bar.classList.remove("is-hidden");
            $("#ac-message-input").focus();
        }

        async quickReact(messageId) {
            const content = "👍";
            await this.toggleReaction(messageId, content, true);
        }

        async toggleReaction(messageId, content, forceAdd = false) {
            const msg = this.currentMessages.find(m => Number(m.id) === Number(messageId));
            const existing = msg?.reactions?.find(r => r.content === content);
            const action = forceAdd ? "add" : (existing?.mine ? "remove" : "add");
            await rpc("/employee_portal/chat/reaction", { thread_id: this.currentThreadId, message_id: messageId, content, action });
            await this.refreshMessages(false);
        }

        queueFiles(fileList) {
            const files = Array.from(fileList || []);
            this.pendingFiles.push(...files.filter(f => f.size <= 10 * 1024 * 1024));
            $("#ac-file-input").value = "";
            this.renderPendingFiles();
        }

        renderPendingFiles() {
            const strip = $("#ac-attachment-strip");
            strip.classList.toggle("is-hidden", !this.pendingFiles.length);
            strip.innerHTML = this.pendingFiles.map((f, i) => `<span class="ac-pending-file"><i class="fa fa-paperclip"></i>${esc(f.name)}<button type="button" data-index="${i}"><i class="fa fa-times"></i></button></span>`).join("");
            $$('button[data-index]', strip).forEach(btn => btn.addEventListener("click", () => { this.pendingFiles.splice(Number(btn.dataset.index), 1); this.renderPendingFiles(); }));
        }

        async uploadFile(file) {
            const data = await this.fileToDataUrl(file);
            const result = await rpc("/employee_portal/chat/upload", { thread_id: this.currentThreadId, filename: file.name || "attachment", mimetype: file.type || "application/octet-stream", data });
            if (result?.error) throw new Error(result.error);
            return result.attachment.id;
        }

        fileToDataUrl(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); }); }

        async sendMessage() {
            if (!this.currentThreadId) return;
            const input = $("#ac-message-input");
            const body = input.value.trim();
            if (!body && !this.pendingFiles.length) return;
            const send = $("#ac-send"); send.disabled = true;
            try {
                const attachmentIds = [];
                for (const file of this.pendingFiles) attachmentIds.push(await this.uploadFile(file));
                const result = await rpc("/employee_portal/chat/send", { thread_id: this.currentThreadId, body, reply_to_id: this.replyTo?.id || false, attachment_ids: attachmentIds });
                if (result?.error) throw new Error(result.error);
                input.value = ""; this.autogrowComposer(); this.pendingFiles = []; this.renderPendingFiles(); this.setReply(null); this.handleTyping(false);
                await this.refreshMessages(true);
            } catch (error) { alert(`Could not send message: ${error.message}`); }
            finally { send.disabled = false; }
        }

        async handleTyping(typing) {
            if (!this.currentThreadId) return;
            if (typing === this.lastTyping && typing) { clearTimeout(this.typingTimer); this.typingTimer = setTimeout(() => this.handleTyping(false), 2500); return; }
            this.lastTyping = typing;
            rpc("/employee_portal/chat/typing", { thread_id: this.currentThreadId, typing }).catch(() => {});
            clearTimeout(this.typingTimer);
            if (typing) this.typingTimer = setTimeout(() => this.handleTyping(false), 2500);
        }

        autogrowComposer() { const el = $("#ac-message-input"); el.style.height = "auto"; el.style.height = `${Math.min(120, el.scrollHeight)}px`; }

        async toggleVoiceRecording() {
            const btn = $("#ac-voice");
            if (this.recorder && this.recorder.state === "recording") { this.recorder.stop(); return; }
            if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { alert("Voice recording is not supported in this browser."); return; }
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                this.recordingChunks = [];
                const options = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? { mimeType: "audio/webm;codecs=opus" } : {};
                this.recorder = new MediaRecorder(stream, options);
                this.recorder.ondataavailable = ev => { if (ev.data?.size) this.recordingChunks.push(ev.data); };
                this.recorder.onstop = () => {
                    const blob = new Blob(this.recordingChunks, { type: this.recorder.mimeType || "audio/webm" });
                    const seconds = Math.max(1, Math.round((Date.now() - this.recordingStartedAt) / 1000));
                    const file = new File([blob], `Voice note ${new Date().toISOString().replace(/[:.]/g, "-")}.webm`, { type: blob.type || "audio/webm" });
                    this.pendingFiles.push(file); this.renderPendingFiles();
                    stream.getTracks().forEach(t => t.stop()); btn.classList.remove("recording"); btn.title = "Voice note";
                    if (seconds > 0) this.sendMessage();
                };
                this.recordingStartedAt = Date.now(); this.recorder.start(); btn.classList.add("recording"); btn.title = "Stop recording";
            } catch (error) { alert(`Microphone access failed: ${error.message}`); }
        }

        async callCurrent(type) {
            const participants = (this.currentThread?.participants || []).filter(p => !p.is_me).map(p => Number(p.user_id)).filter(Boolean);
            if (!participants.length) return;
            const caller = await this.waitForCaller();
            if (!caller) { alert("Call service is still loading. Please try again."); return; }
            if (participants.length === 1) caller._startCall(participants[0], type);
            else caller._startHistoryGroupCall(participants, type);
        }

        waitForCaller() { return new Promise(resolve => { let tries = 0; const check = () => { if (window.__employeePortalCaller) return resolve(window.__employeePortalCaller); if (++tries > 30) return resolve(null); setTimeout(check, 100); }; check(); }); }

        async refreshCallHistory() {
            const box = $("#ac-call-history");
            try {
                const result = await rpc("/employee_portal/call/history", { limit: 80 });
                const calls = result?.calls || [];
                const unread = Number(result?.unread_missed_count || 0);
                $("#ac-call-badge").textContent = unread > 99 ? "99+" : unread; $("#ac-call-badge").classList.toggle("is-hidden", !unread);
                box.innerHTML = calls.length ? calls.map(c => `<div class="ac-call-row ${c.status === 'missed' ? 'missed' : ''}" data-call='${JSON.stringify(c).replace(/'/g,"&#39;")}'><img src="${esc(c.avatar_url || '/absar_chat_pwa/static/icons/icon-192.png')}" alt=""/><div class="ac-call-copy"><strong>${esc(c.title || "Employee")}</strong><span>${esc(this.callStatus(c))} · ${esc(this.formatListTime(c.started_at))}${c.duration_seconds ? ` · ${this.formatDuration(c.duration_seconds)}` : ""}</span></div><div class="ac-call-actions"><button class="ac-icon-btn" data-callback="audio" title="Call"><i class="fa fa-phone"></i></button><button class="ac-icon-btn" data-callback="video" title="Video call"><i class="fa fa-video-camera"></i></button></div></div>`).join("") : `<div class="ac-loading">No calls yet.</div>`;
                $$("[data-callback]", box).forEach(btn => btn.addEventListener("click", async () => { const row = btn.closest(".ac-call-row"); const c = JSON.parse(row.dataset.call); const ids = (c.callback_user_ids || []).map(Number).filter(Boolean); const caller = await this.waitForCaller(); if (!caller || !ids.length) return; if (ids.length === 1) caller._startCall(ids[0], btn.dataset.callback); else caller._startHistoryGroupCall(ids, btn.dataset.callback); }));
                await rpc("/employee_portal/call/history/mark_seen", {}).catch(() => {});
            } catch (error) { box.innerHTML = `<div class="ac-error">Could not load call history.</div>`; }
        }

        callStatus(c) { const map = {completed:c.direction === "outgoing"?"Outgoing":"Incoming",missed:"Missed",declined:"Declined",no_answer:"No answer",ringing:"Ringing",ongoing:"In progress"}; return map[c.status] || "Call"; }
        formatDuration(seconds) { const s = Number(seconds || 0), m = Math.floor(s/60); return m ? `${m}m ${String(s%60).padStart(2,"0")}s` : `${s}s`; }

        renderPeople() {
            const box = $("#ac-people-list"); if (!box) return;
            const q = ($("#ac-people-search").value || "").trim().toLowerCase();
            const rows = this.contacts.filter(c => !q || `${c.name} ${c.department} ${c.note}`.toLowerCase().includes(q));
            box.innerHTML = rows.length ? rows.map(c => `<article class="ac-person-card"><img src="${esc(c.avatar_url)}" alt=""/><div class="ac-person-copy"><strong>${esc(c.name)}</strong><span>${esc(c.note || c.department || c.user_type || "Employee")}</span><span>${esc(this.presenceLabel(c.presence))}</span></div><div class="ac-person-actions"><button class="ac-icon-btn" data-chat-user="${c.user_id}" title="Message"><i class="fa fa-comment"></i></button><button class="ac-icon-btn" data-call-user="${c.user_id}" data-type="audio" title="Call"><i class="fa fa-phone"></i></button></div></article>`).join("") : `<div class="ac-loading">No employees found.</div>`;
            $$('[data-chat-user]', box).forEach(btn => btn.addEventListener("click", () => this.startDirect(Number(btn.dataset.chatUser))));
            $$('[data-call-user]', box).forEach(btn => btn.addEventListener("click", async () => { const caller = await this.waitForCaller(); caller?._startCall(Number(btn.dataset.callUser), btn.dataset.type || "audio"); }));
        }

        openNewChat() { this.modalMode = "new"; this.modalPeople = null; this.selectedPeople.clear(); $("#ac-new-search").value = ""; $("#ac-group-name").value = ""; $("#ac-new-modal h3").textContent = "New conversation"; $("#ac-new-modal header p").textContent = "Select one employee for a direct chat or several for a group."; $("#ac-new-start").textContent = "Start conversation"; this.renderNewPeople(); $("#ac-modal-backdrop").classList.remove("is-hidden"); $("#ac-new-modal").classList.remove("is-hidden"); setTimeout(() => $("#ac-new-search").focus(), 40); }
        closeNewChat() { $("#ac-modal-backdrop").classList.add("is-hidden"); $("#ac-new-modal").classList.add("is-hidden"); }
        renderNewPeople() {
            const box = $("#ac-new-people"); if (!box) return;
            const q = ($("#ac-new-search").value || "").trim().toLowerCase();
            const source = this.modalPeople || this.contacts;
            const rows = source.filter(c => !q || `${c.name} ${c.department || ""} ${c.note || ""}`.toLowerCase().includes(q));
            box.innerHTML = rows.map(c => `<label class="ac-select-person"><img src="${esc(c.avatar_url)}" alt=""/><div><strong>${esc(c.name)}</strong><span>${esc(c.note || c.department || "Employee")} · ${esc(this.presenceLabel(c.presence))}</span></div><input type="checkbox" value="${c.user_id}" ${this.selectedPeople.has(Number(c.user_id)) ? "checked" : ""}/></label>`).join("");
            $$('input[type="checkbox"]', box).forEach(cb => cb.addEventListener("change", () => { const id = Number(cb.value); cb.checked ? this.selectedPeople.add(id) : this.selectedPeople.delete(id); this.updateNewSelection(); }));
            this.updateNewSelection();
        }
        updateNewSelection() { const n = this.selectedPeople.size; $("#ac-new-count").textContent = `${n} selected`; $("#ac-new-start").disabled = n === 0; $("#ac-group-name").classList.toggle("is-hidden", n < 2); }
        async startConversation() {
            const ids = Array.from(this.selectedPeople); if (!ids.length) return;
            if (this.modalMode === "add") {
                const channelId = this.currentThread?.discuss_channel_id;
                const result = await rpc("/employee_portal/discuss/add_people", { channel_id: channelId, user_ids: ids });
                if (!result?.ok) { alert(result?.error || "Could not add people."); return; }
                this.closeNewChat(); this.modalMode = "new"; this.modalPeople = null;
                await this.refreshThreads(false);
                const thread = this.threads.find(t => Number(t.discuss_channel_id) === Number(result.channel_id));
                if (thread) await this.openThread(Number(thread.id)); else await this.refreshMessages(true);
                return;
            }
            const name = $("#ac-group-name").value.trim();
            const result = await rpc("/employee_portal/chat/start", { participant_ids: ids, name });
            if (result?.error) { alert(result.error); return; }
            this.closeNewChat(); await this.refreshThreads(false); if (result.thread_id) this.openThread(Number(result.thread_id));
        }
        async startDirect(userId) { const result = await rpc("/employee_portal/chat/start", { participant_ids: [userId] }); if (result?.thread_id) { await this.refreshThreads(false); this.setView("chats"); this.openThread(Number(result.thread_id)); } }

        toggleInfo(show) { $("#ac-info-panel").classList.toggle("is-hidden", !show); if (show) this.renderInfo(); }
        renderInfo() {
            const box = $("#ac-info-content"); if (!box || !this.currentThread) return;
            const t = this.currentThread, participants = t.participants || [];
            const threadAvatar = this.threads.find(x => Number(x.id) === Number(this.currentThreadId))?.avatar_url || "/absar_chat_pwa/static/icons/icon-192.png";
            box.innerHTML = `<div class="ac-info-profile"><img src="${esc(threadAvatar)}" alt=""/><h3>${esc(t.name || "Conversation")}</h3><p>${t.is_group ? `${t.participant_count || participants.length} participants` : "Direct conversation"}</p></div><div class="ac-info-section"><h4>Participants</h4>${participants.map(p => `<div class="ac-participant"><img src="${esc(p.avatar_url)}" alt=""/><div><strong>${esc(p.name)}${p.is_me ? " (You)" : ""}</strong><span>${p.is_me ? "Online" : esc(this.presenceLabel(this.presence[String(p.user_id)] || "offline"))}</span></div></div>`).join("")}${t.discuss_channel_id ? `<button id="ac-add-people" class="ac-secondary-btn" style="width:100%;margin-top:10px"><i class="fa fa-user-plus"></i> Add people</button>` : ""}</div>`;
            $("#ac-add-people")?.addEventListener("click", () => this.addPeopleToCurrent());
        }

        async addPeopleToCurrent() {
            const channelId = this.currentThread?.discuss_channel_id; if (!channelId) return;
            const result = await rpc("/employee_portal/discuss/available_people", { channel_id: channelId });
            const people = (result?.people || []).map(p => ({ user_id: p.id, name: p.name, avatar_url: p.avatar, department: "", note: "Employee", presence: this.presence[String(p.id)] || "offline" }));
            if (!people.length) { alert("Everyone available is already in this conversation."); return; }
            this.modalMode = "add"; this.modalPeople = people; this.selectedPeople.clear();
            $("#ac-new-search").value = ""; $("#ac-group-name").classList.add("is-hidden");
            $("#ac-new-modal h3").textContent = "Add people";
            $("#ac-new-modal header p").textContent = "Select employees to add to this conversation.";
            $("#ac-new-start").textContent = "Add selected";
            this.renderNewPeople(); $("#ac-modal-backdrop").classList.remove("is-hidden"); $("#ac-new-modal").classList.remove("is-hidden");
        }

        startTimers() {
            const threadTick = async () => { if (document.visibilityState === "visible") await this.refreshThreads(true).catch(() => {}); this.threadTimer = setTimeout(threadTick, 5000); };
            const messageTick = async () => { if (document.visibilityState === "visible" && this.currentThreadId) await this.refreshMessages(false); this.messageTimer = setTimeout(messageTick, 2500); };
            const presenceTick = async () => { if (document.visibilityState === "visible") await this.refreshPresence(); this.presenceTimer = setTimeout(presenceTick, 15000); };
            this.threadTimer = setTimeout(threadTick, 5000); this.messageTimer = setTimeout(messageTick, 2500); this.presenceTimer = setTimeout(presenceTick, 15000);
        }
        syncNow() { this.refreshThreads(false).catch(() => {}); this.refreshPresence().catch(() => {}); if (this.currentThreadId) this.refreshMessages(false); }

        async installApp() { if (this.deferredInstall) { this.deferredInstall.prompt(); await this.deferredInstall.userChoice; this.deferredInstall = null; } else alert("Use your browser's Install / Add to Home Screen option to install Absar Chat."); }
        async enableNotifications() { if (!("Notification" in window)) return alert("Notifications are not supported by this browser."); const p = await Notification.requestPermission(); $("#ac-notifications").textContent = p === "granted" ? "Enabled" : "Enable"; }
        notify(title, body) { if ("Notification" in window && Notification.permission === "granted") { try { new Notification(title, { body, icon: "/absar_chat_pwa/static/icons/icon-192.png" }); } catch (_) {} } }

        scrollMessagesToBottom() { const box = $("#ac-messages"); requestAnimationFrame(() => { box.scrollTop = box.scrollHeight; }); }
        formatBytes(bytes) { const n = Number(bytes || 0); if (!n) return ""; if (n < 1024) return `${n} B`; if (n < 1048576) return `${(n/1024).toFixed(1)} KB`; return `${(n/1048576).toFixed(1)} MB`; }
        parseDate(value) { if (!value) return null; const v = value.includes("T") ? value : value.replace(" ", "T") + "Z"; const d = new Date(v); return Number.isNaN(d.getTime()) ? null : d; }
        formatTime(value) { const d = this.parseDate(value); return d ? d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}) : ""; }
        dateKey(value) { const d = this.parseDate(value); return d ? d.toDateString() : ""; }
        formatDay(value) { const d = this.parseDate(value); if (!d) return ""; const today = new Date(); const yesterday = new Date(); yesterday.setDate(today.getDate()-1); if (d.toDateString() === today.toDateString()) return "Today"; if (d.toDateString() === yesterday.toDateString()) return "Yesterday"; return d.toLocaleDateString([], {weekday:"short",month:"short",day:"numeric"}); }
        formatListTime(value) { const d = this.parseDate(value); if (!d) return ""; const now = new Date(); return d.toDateString() === now.toDateString() ? d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}) : d.toLocaleDateString([], {month:"short",day:"numeric"}); }
        presenceLabel(value) { return ({online:"Online",away:"Away",in_call:"In a call",offline:"Offline"})[value] || "Offline"; }
    }

    document.addEventListener("DOMContentLoaded", () => { window.__absarChat = new AbsarChat(); });
})();
