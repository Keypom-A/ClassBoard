// ================================
//  chat.js（ClassBoard 完全版）
// ================================

document.addEventListener("DOMContentLoaded", () => {

    // ===== テーマ適用 =====
    if (localStorage.getItem('theme') === 'dark') {
        document.documentElement.classList.add('dark-theme');
    }

    // ===== メニュー開閉 =====
    window.toggleMenu = function () {
        document.getElementById('sidebar').classList.toggle('open');
        document.getElementById('overlay').classList.toggle('open');
    };

    // ===== 初期スクロール =====
    const chatDisplay = document.getElementById('chatDisplay');
    if (chatDisplay) {
        chatDisplay.scrollTop = chatDisplay.scrollHeight;
    }

    // ===== グループ作成 =====
    window.createGroup = function () {
        const name = prompt("新しいグループの合言葉を決めてください");
        if (name) location.href = "/chat?group=" + encodeURIComponent(name);
    };

    // ===== グループ参加 =====
    window.joinGroup = function () {
        const name = prompt("参加するグループの合言葉を入力してください");
        if (name) location.href = "/chat?group=" + encodeURIComponent(name);
    };

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
            div.innerHTML = `
                <div class="user-name">${msg.sender}</div>
                <div style="word-break: break-all;">${msg.text}</div>
            `;
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
    //  新着メッセージ検知（DM + GRP）
    // ================================
    function detectNewMessages(unread) {
        if (!lastUnread) return;

        // --- DM ---
        if (window.currentPartner) {
            const p = window.currentPartner;
            const prev = lastUnread[p] || 0;
            const now = unread[p] || 0;
            if (now > prev) refreshMessages();
            return;
        }

        // --- グループ ---
        if (window.currentGroup) {
            const g = window.currentGroup;
            const prev = lastUnread[g] || 0;
            const now = unread[g] || 0;
            if (now > prev) refreshMessages();
            return;
        }

        // --- 全体チャット ---
        const prevAll = lastUnread["all"] || 0;
        const nowAll = unread["all"] || 0;
        if (nowAll > prevAll) refreshMessages();
    }

    // ===== 未読数の定期更新 =====
    setInterval(updateUnreadBadges, 3000);
    updateUnreadBadges();

    // ================================
    //  即時反映（送信した瞬間に吹き出し追加）
    // ================================
    function appendMyMessage(text) {
        const chatDisplay = document.getElementById("chatDisplay");

        const row = document.createElement("div");
        row.className = "msg-row";

        const msg = document.createElement("div");
        msg.className = "message my-msg";

        msg.innerHTML = `
            <div class="user-name">${window.username}</div>
            <div style="word-break: break-all;">${text}</div>
        `;

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
            if (!msg) return;

            // 即時反映
            appendMyMessage(msg);

            messageInput.value = "";

            // サーバーへ送信
            await fetch("/send_message", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: msg })
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
