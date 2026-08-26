/**
 * Employee Portal Suite - Calling widget.
 *
 * Deliberately framework-light (no OWL/publicWidget/bus_service dependency)
 * so the exact same file can be loaded in both web.assets_frontend (portal)
 * and web.assets_backend (internal users) and behave identically.
 *
 * Signalling is done by polling /employee_portal/call/poll every 2s rather
 * than using the mail bus, to keep this fully decoupled from Discuss/RTC
 * internals. See portal_call.py controller docstring for the tradeoffs.
 */
(function () {
    "use strict";

    const POLL_INTERVAL_MS = 2000;

    async function rpc(route, params) {
        const resp = await fetch(route, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: params || {},
                id: Math.floor(Math.random() * 1e9),
            }),
        });
        const json = await resp.json();
        if (json.error) {
            console.error("[EPC] RPC error", json.error);
            throw new Error(json.error.data ? json.error.data.message : "RPC error");
        }
        return json.result;
    }

    class EmployeePortalCaller {
        constructor() {
            this.lastId = 0;
            this.pollTimer = null;
            this.pc = null;
            this.localStream = null;
            this.currentUuid = null;
            this.currentCallType = "audio";
            this.iceServers = [{ urls: ["stun:stun.l.google.com:19302"] }];
            this.contacts = [];
            this._buildUI();
            this._loadContacts();
            this._startPolling();
        }

        // ------------------------------------------------------------
        // UI scaffolding (framework independent, injected once)
        // ------------------------------------------------------------
        _buildUI() {
            const root = document.createElement("div");
            root.id = "epc-root";
            root.innerHTML = `
                <button id="epc-fab" class="epc-fallback-fab epc-hidden" title="Call" aria-label="Call"><i class="fa fa-phone"></i></button>
                <div id="epc-panel" class="epc-hidden">
                    <div class="epc-panel-header">
                        <span>Call a user</span>
                        <button id="epc-panel-close">&times;</button>
                    </div>
                    <div class="epc-search-wrap"><input id="epc-contact-search" type="search" placeholder="Search users…" autocomplete="off"/></div>
                    <div id="epc-contact-list"><div class="epc-empty">Loading…</div></div>
                </div>
                <div id="epc-incoming" class="epc-hidden">
                    <div class="epc-incoming-name"></div>
                    <div class="epc-incoming-sub">Incoming call…</div>
                    <div class="epc-incoming-actions">
                        <button id="epc-accept" class="epc-btn epc-btn-accept">Accept</button>
                        <button id="epc-reject" class="epc-btn epc-btn-reject">Decline</button>
                    </div>
                </div>
                <div id="epc-active" class="epc-hidden">
                    <div class="epc-active-name"></div>
                    <div class="epc-active-status">Connecting…</div>
                    <video id="epc-remote-video" autoplay playsinline></video>
                    <video id="epc-local-video" autoplay playsinline muted></video>
                    <div class="epc-active-actions">
                        <button id="epc-mute" class="epc-btn">Mute</button>
                        <button id="epc-hangup" class="epc-btn epc-btn-reject">Hang up</button>
                    </div>
                </div>
            `;
            document.body.appendChild(root);

            // On employee portal pages, place the call control directly beside
            // every notification bell (desktop and mobile versions both exist
            // in the DOM and CSS chooses the visible header). Backend pages do
            // not have that header, so they keep a floating fallback button.
            const bellWraps = Array.from(document.querySelectorAll(".ep-bell-wrap"));
            if (bellWraps.length) {
                bellWraps.forEach((bellWrap) => {
                    if (bellWrap.parentElement && bellWrap.parentElement.querySelector(":scope > .epc-header-btn")) return;
                    const btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = "epc-header-btn";
                    btn.title = "Calls";
                    btn.setAttribute("aria-label", "Calls");
                    btn.innerHTML = '<i class="fa fa-phone"></i>';
                    bellWrap.insertAdjacentElement("beforebegin", btn);
                    btn.addEventListener("click", (ev) => {
                        ev.stopPropagation();
                        this._togglePanel(btn);
                    });
                });
            } else {
                const fab = document.getElementById("epc-fab");
                fab.classList.remove("epc-hidden");
                fab.addEventListener("click", (ev) => {
                    ev.stopPropagation();
                    this._togglePanel(fab);
                });
            }
            document.getElementById("epc-panel-close").addEventListener("click", () => {
                document.getElementById("epc-panel").classList.add("epc-hidden");
            });
            document.getElementById("epc-accept").addEventListener("click", () => this._acceptIncoming());
            document.getElementById("epc-reject").addEventListener("click", () => this._rejectIncoming());
            document.getElementById("epc-hangup").addEventListener("click", () => this._hangup());
            document.getElementById("epc-mute").addEventListener("click", () => this._toggleMute());
            document.getElementById("epc-contact-search").addEventListener("input", () => this._renderContacts());

            document.addEventListener("click", (ev) => {
                const panel = document.getElementById("epc-panel");
                if (!panel.classList.contains("epc-hidden") &&
                    !ev.target.closest("#epc-panel") &&
                    !ev.target.closest(".epc-header-btn") &&
                    !ev.target.closest("#epc-fab")) {
                    panel.classList.add("epc-hidden");
                }
            });
            window.addEventListener("resize", () => {
                const panel = document.getElementById("epc-panel");
                if (!panel.classList.contains("epc-hidden") && this._panelAnchor) {
                    this._positionPanel(this._panelAnchor);
                }
            });
        }

        _togglePanel(anchor) {
            const panel = document.getElementById("epc-panel");
            const opening = panel.classList.contains("epc-hidden");
            if (opening) {
                this._panelAnchor = anchor;
                panel.classList.remove("epc-hidden");
                this._positionPanel(anchor);
                const search = document.getElementById("epc-contact-search");
                if (search) setTimeout(() => search.focus(), 0);
            } else {
                panel.classList.add("epc-hidden");
            }
        }

        _positionPanel(anchor) {
            const panel = document.getElementById("epc-panel");
            if (!anchor || !panel) return;
            const rect = anchor.getBoundingClientRect();
            const gap = 10;
            const edge = 12;
            panel.style.top = `${Math.max(edge, rect.bottom + gap)}px`;
            panel.style.bottom = "auto";
            panel.style.right = `${Math.max(edge, window.innerWidth - rect.right)}px`;
            panel.style.left = "auto";
            const maxHeight = Math.max(220, window.innerHeight - rect.bottom - gap - edge);
            panel.style.maxHeight = `${Math.min(430, maxHeight)}px`;
        }

        async _loadContacts() {
            try {
                this.contacts = await rpc("/employee_portal/call/contacts", {});
            } catch (e) {
                this.contacts = [];
            }
            this._renderContacts();
        }

        _renderContacts() {
            const list = document.getElementById("epc-contact-list");
            const search = document.getElementById("epc-contact-search");
            const term = (search ? search.value : "").trim().toLowerCase();
            const contacts = this.contacts.filter((c) =>
                !term || (c.name || "").toLowerCase().includes(term) ||
                (c.user_type || "").toLowerCase().includes(term)
            );

            list.innerHTML = "";
            if (!contacts.length) {
                list.innerHTML = `<div class="epc-empty">${term ? "No matching users." : "No other active users found."}</div>`;
                return;
            }
            contacts.forEach((c) => {
                const row = document.createElement("div");
                row.className = "epc-contact-row";
                const identity = document.createElement("div");
                identity.className = "epc-contact-identity";
                identity.innerHTML = `<span class="epc-contact-name">${this._escape(c.name)}</span>` +
                    `<span class="epc-contact-type">${this._escape(c.user_type || "User")}</span>`;
                const callBtn = document.createElement("button");
                callBtn.textContent = "Call";
                callBtn.className = "epc-btn epc-btn-small";
                callBtn.addEventListener("click", () => this._startCall(c.user_id));
                row.appendChild(identity);
                row.appendChild(callBtn);
                list.appendChild(row);
            });
        }

        _escape(s) {
            const d = document.createElement("div");
            d.textContent = s || "";
            return d.innerHTML;
        }

        // ------------------------------------------------------------
        // Polling loop
        // ------------------------------------------------------------
        _startPolling() {
            const tick = async () => {
                try {
                    const res = await rpc("/employee_portal/call/poll", { last_id: this.lastId });
                    this.lastId = res.last_id;
                    for (const evt of res.events) {
                        await this._handleEvent(evt);
                    }
                } catch (e) {
                    // network hiccup / session expiry: keep polling silently
                }
                this.pollTimer = setTimeout(tick, POLL_INTERVAL_MS);
            };
            tick();
        }

        async _handleEvent(evt) {
            if (evt.event === "incoming") {
                this.currentUuid = evt.uuid;
                this.currentCallType = evt.payload.call_type || "audio";
                document.querySelector("#epc-incoming .epc-incoming-name").textContent =
                    evt.payload.caller_name || "Unknown";
                document.getElementById("epc-incoming").classList.remove("epc-hidden");
            } else if (evt.event === "signal" && evt.uuid === this.currentUuid) {
                await this._handleSignal(evt.payload);
            } else if (evt.event === "accepted" && evt.uuid === this.currentUuid) {
                document.querySelector("#epc-active .epc-active-status").textContent = "Connected";
                await this._createOfferIfCaller();
            } else if (["rejected", "ended", "cancelled"].includes(evt.event) && evt.uuid === this.currentUuid) {
                this._teardown();
            }
        }

        // ------------------------------------------------------------
        // Call actions
        // ------------------------------------------------------------
        async _startCall(targetUserId) {
            try {
                const res = await rpc("/employee_portal/call/start", {
                    target_user_id: targetUserId,
                    call_type: "audio",
                });
                if (res.error) {
                    alert("Could not start call: " + res.error);
                    return;
                }
                this.currentUuid = res.uuid;
                this._iAmCaller = true;
                document.getElementById("epc-panel").classList.add("epc-hidden");
                await this._prepareLocalMedia();
                this._showActive("Calling…");
            } catch (e) {
                alert("Could not start call.");
            }
        }

        async _acceptIncoming() {
            if (!this.currentUuid) return;
            document.getElementById("epc-incoming").classList.add("epc-hidden");
            this._iAmCaller = false;
            await this._prepareLocalMedia();
            await this._createPeerConnection();
            this._showActive("Connecting…");
            await rpc("/employee_portal/call/accept", { uuid: this.currentUuid });
        }

        async _rejectIncoming() {
            if (!this.currentUuid) return;
            await rpc("/employee_portal/call/reject", { uuid: this.currentUuid });
            document.getElementById("epc-incoming").classList.add("epc-hidden");
            this.currentUuid = null;
        }

        async _hangup() {
            if (this.currentUuid) {
                await rpc("/employee_portal/call/end", { uuid: this.currentUuid });
            }
            this._teardown();
        }

        _toggleMute() {
            if (!this.localStream) return;
            this.localStream.getAudioTracks().forEach((t) => (t.enabled = !t.enabled));
        }

        _showActive(status) {
            document.getElementById("epc-active").classList.remove("epc-hidden");
            document.querySelector("#epc-active .epc-active-status").textContent = status;
        }

        _teardown() {
            if (this.pc) {
                this.pc.close();
                this.pc = null;
            }
            if (this.localStream) {
                this.localStream.getTracks().forEach((t) => t.stop());
                this.localStream = null;
            }
            document.getElementById("epc-active").classList.add("epc-hidden");
            document.getElementById("epc-incoming").classList.add("epc-hidden");
            this.currentUuid = null;
        }

        // ------------------------------------------------------------
        // WebRTC
        // ------------------------------------------------------------
        async _prepareLocalMedia() {
            try {
                this.localStream = await navigator.mediaDevices.getUserMedia({
                    audio: true,
                    video: this.currentCallType === "video",
                });
                document.getElementById("epc-local-video").srcObject = this.localStream;
            } catch (e) {
                alert("Microphone/camera access is required to make a call.");
                throw e;
            }
        }

        async _createPeerConnection() {
            try {
                const res = await rpc("/employee_portal/call/ice_servers", {});
                this.iceServers = res.iceServers || this.iceServers;
            } catch (e) {
                /* fall back to default STUN */
            }
            this.pc = new RTCPeerConnection({ iceServers: this.iceServers });
            this.localStream.getTracks().forEach((t) => this.pc.addTrack(t, this.localStream));
            this.pc.ontrack = (ev) => {
                document.getElementById("epc-remote-video").srcObject = ev.streams[0];
            };
            this.pc.onicecandidate = (ev) => {
                if (ev.candidate) {
                    rpc("/employee_portal/call/signal", {
                        uuid: this.currentUuid,
                        signal_type: "ice",
                        data: ev.candidate,
                    });
                }
            };
        }

        async _createOfferIfCaller() {
            if (!this._iAmCaller) return;
            await this._createPeerConnection();
            const offer = await this.pc.createOffer();
            await this.pc.setLocalDescription(offer);
            await rpc("/employee_portal/call/signal", {
                uuid: this.currentUuid,
                signal_type: "offer",
                data: offer,
            });
        }

        async _handleSignal(payload) {
            if (!payload) return;
            const { signal_type, data } = payload;
            if (signal_type === "offer") {
                if (!this.pc) await this._createPeerConnection();
                await this.pc.setRemoteDescription(new RTCSessionDescription(data));
                const answer = await this.pc.createAnswer();
                await this.pc.setLocalDescription(answer);
                await rpc("/employee_portal/call/signal", {
                    uuid: this.currentUuid,
                    signal_type: "answer",
                    data: answer,
                });
            } else if (signal_type === "answer") {
                if (this.pc) await this.pc.setRemoteDescription(new RTCSessionDescription(data));
            } else if (signal_type === "ice") {
                if (this.pc) {
                    try {
                        await this.pc.addIceCandidate(new RTCIceCandidate(data));
                    } catch (e) {
                        /* candidate arrived before remote description; safe to ignore */
                    }
                }
            }
        }
    }

    function shouldMount() {
        // Backend: web client wrapper is always present for logged-in internal users.
        if (document.querySelector(".o_web_client")) {
            return true;
        }
        // Frontend/portal: only mount on actual portal pages for logged-in portal
        // users, never on public/anonymous website pages.
        const isPortalPage = document.body.classList.contains("o_portal") ||
            !!document.getElementById("epc-mount-marker");
        const isLoggedIn = document.body.getAttribute("data-epc-logged-in") === "1" ||
            !!document.getElementById("epc-mount-marker");
        return isPortalPage && isLoggedIn;
    }

    document.addEventListener("DOMContentLoaded", () => {
        if (shouldMount()) {
            window.__employeePortalCaller = new EmployeePortalCaller();
        }
    });
})();
