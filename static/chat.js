// ================================
//  chat.js（ClassBoard 完全版）
// ================================

document.addEventListener("DOMContentLoaded", () => {

    // ===== テーマ適用 =====
    if (localStorage.getItem('theme') === 'dark') {
        document.documentElement.classList.add('dark-theme');
    }

    // ===== メニュー開閉（スマホ用） =====
    window.toggleMenu = function () {
        document.getElementById('sidebar').classList.toggle('open');
        document.getElementById('overlay').classList.toggle('open');
    };

    // ===== 初期スクロール =====
    const chatDisplay = document.getElementById('chatDisplay');
    if (chatDisplay) {
        chatDisplay.scrollTop = chatDisplay.scrollHeight;
    }

    // ================================
    //  メッセージ欄だけ更新（API版）
    // ================================
    async function refreshMessages() {
        const res = await fetch(`/api/messages${location.search}`);
        const messages = await res.json();

        const box = document.getElementById("chatDisplay");
        box.innerHTML = "";

        messages.forEach(msg => {
            const row = document.createElement("div");
            row.className = "msg-row";

            const div = document.createElement("div");
            div.className = msg.is_me ? "message my-msg" : "message other-msg";

            let html = `
                <div class="user-name">${msg.sender}</div>
            `;

            if (msg.file_path) {
                html += `<img src="${msg.file_path}" style="max-width:200px;border-radius:8px;">`;
            }

            html += `<div style="word-break: break-all;">${msg.text}</div>`;

            div.innerHTML = html;
            row.appendChild(div);
            box.appendChild(row);
        });

        box.scrollTop = box.scrollHeight;
    }

    // ================================
    //  未読バッジ更新
    // ================================
    let lastUnread = null;

    async function updateUnreadBadges() {
        const res = await fetch("/api/unread_count");
        const data = await res.json();
        const unread = data.unread || {};

        // --- バッジ更新 ---
        document.querySelectorAll(".chat-link").forEach(link => {
            const rx = link.dataset.rx; // "all" or username or group
            const badge = link.querySelector(".badge-notify");
            if (!badge) return;

            const count = unread[rx] || 0;

            badge.style.display = count > 0 ? "inline-flex" : "none";
            badge.textContent = count > 0 ? count : "";
        });

        // --- 新着検知 ---
        detectNewMessages(unread);

        lastUnread = unread;
    }

    // ================================
    //  新着メッセージ検知（DM + GRP + ALL）
    // ================================
    function detectNewMessages(unread) {
        if (!lastUnread) return;

        // --- DM ---
        if (window.currentPartner) {
            const p = window.currentPartner;
            if ((unread[p] || 0) > (lastUnread[p] || 0)) {
                refreshMessages();
            }
            return;
        }

        // --- グループ ---
        if (window.currentGroup) {
            const g = window.currentGroup;
            if ((unread[g] || 0) > (lastUnread[g] || 0)) {
                refreshMessages();
            }
            return;
        }

        // --- 全体チャット ---
        if ((unread["all"] || 0) > (lastUnread["all"] || 0)) {
            refreshMessages();
        }
    }

    // ===== 未読数の定期更新 =====
    setInterval(updateUnreadBadges, 3000);
    updateUnreadBadges();

    // ================================
    //  即時反映（送信した瞬間に吹き出し追加）
    // ================================
    function appendMyMessage(text, fileUrl = null) {
        const chatDisplay = document.getElementById("chatDisplay");

        const row = document.createElement("div");
        row.className = "msg-row";

        const msg = document.createElement("div");
        msg.className = "message my-msg";

        let html = `
            <div class="user-name">${window.username}</div>
        `;

        if (fileUrl) {
            html += `<img src="${fileUrl}" style="max-width:200px;border-radius:8px;">`;
        }

        html += `<div style="word-break: break-all;">${text}</div>`;

        msg.innerHTML = html;

        row.appendChild(msg);
        chatDisplay.appendChild(row);

        chatDisplay.scrollTop = chatDisplay.scrollHeight;
    }

    // ================================
    //  送信イベント
    // ================================
    const sendForm = document.getElementById("sendForm");
    const messageInput = document.getElementById("messageInput");

    if (sendForm) {
        sendForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            const msg = messageInput.value.trim();
            const fileInput = sendForm.querySelector("input[type='file']");
            const file = fileInput?.files[0] || null;

            if (!msg && !file) return;

            // 即時反映（画像は Cloudinary アップ後に反映）
            appendMyMessage(msg);

            const formData = new FormData(sendForm);

            messageInput.value = "";
            if (fileInput) fileInput.value = "";

            await fetch(location.href, {
                method: "POST",
                body: formData
            });

            // サーバー側の反映は自動更新に任せる
        });
    }

    // ================================
    //  メッセージ削除
    // ================================
    document.addEventListener("click", async (e) => {
        if (e.target.classList.contains("delete-btn")) {
            const id = e.target.dataset.id;

            if (!confirm("このメッセージを削除しますか？")) return;

            await fetch(`/api/delete_message/${id}`, {
                method: "DELETE"
            });

            refreshMessages();
        }
    });

});
